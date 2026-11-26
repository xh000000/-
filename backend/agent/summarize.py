"""研报 AI 摘要卡：核心观点 + 逻辑链 + 数据要点（对标东证「繁微」的研报秒读）。

一次 LLM 调用产出固定结构的 JSON 摘要，写进 ``reports.ai_summary`` 列并留痕；
列表接口（/api/state）随 to_dict 自动带出，前端不用点开全文就能预览要点。
摘要只是辅助阅读，不参与审批与发布口径。
"""
from __future__ import annotations

import json
import re
import time

import db
from db import Report

_MAX_BODY = 9000        # 送入模型的正文上限（字符）
_SYSTEM = ('你是期货公司研究所的研报摘要助手。只输出一个 JSON 对象，'
           '不要输出解释、不要用 Markdown 代码块。')
_PROMPT = '''请阅读以下研报正文，生成三段式摘要卡，JSON 字段如下：
- "core"：核心观点，一句话（不超过 80 字），概括报告的方向性结论；
- "logic"：逻辑链，不超过 200 字，按「因为…（数据/事件）→ 所以…（传导）→ 因此…（结论）」的因果顺序简述；
- "data"：数据要点数组，2~4 条，每条一条（格式如「螺纹钢库存 512 万吨（11-20），环比 -3.2%」），只能引用正文出现过的数字与日期，禁止编造。

研报标题：{title}

研报正文：
{body}'''


def _stamp() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()) + ' UTC'


def _extract_json(text: str) -> dict:
    """容错解析：剥掉代码围栏、截取首尾大括号。"""
    text = re.sub(r'^```(?:json)?|```$', '', text.strip(), flags=re.MULTILINE).strip()
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end <= start:
        raise ValueError('模型未返回 JSON')
    parsed = json.loads(text[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError('模型返回的不是 JSON 对象')
    return parsed


def _normalize(parsed: dict) -> dict:
    core = str(parsed.get('core') or '').strip()[:200]
    logic = str(parsed.get('logic') or '').strip()[:500]
    data = parsed.get('data')
    if isinstance(data, str):
        data = [data.strip()]
    if not isinstance(data, list):
        data = []
    data = [str(x).strip()[:120] for x in data if str(x).strip()][:4]
    if not core:
        raise ValueError('摘要缺少核心观点')
    return {'core': core, 'logic': logic, 'data': data}


def generate(s, user: dict, report_id) -> dict:
    """为研报生成摘要卡并落库；返回摘要 dict。"""
    import app as platform
    import manual_engine as manual
    import agent.config as config
    import agent.service as service

    if user['role'] not in ('admin', 'researcher'):
        raise PermissionError('仅研究人员与管理员可生成 AI 摘要')

    report = s.get(Report, int(report_id or 0))
    if not report or report.deleted:
        raise ValueError('研报不存在')
    if not manual.can_view(s, report, user):
        raise PermissionError('无权访问此报告')

    cfg_model = config.resolve(service.fallback_profile(s))
    if not config.ready(cfg_model):
        raise ValueError('Agent 模型未配置：请设置 AGENT_API_KEY/AGENT_MODEL 或配置平台外部模型')

    body = (report.body or '').strip()[:_MAX_BODY]
    if len(body) < 50:
        raise ValueError('正文内容过短，无法生成有效摘要')

    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model=cfg_model['model'], api_key=cfg_model['api_key'],
                     base_url=cfg_model['base_url'], temperature=0.2,
                     timeout=cfg_model.get('timeout', 180), max_retries=1)
    answer = llm.invoke([('system', _SYSTEM),
                         ('human', _PROMPT.format(title=report.title, body=body))])
    content = answer.content
    if isinstance(content, list):
        content = ''.join(b.get('text', '') if isinstance(b, dict) else str(b) for b in content)
    summary = _normalize(_extract_json(content))
    summary['at'] = _stamp()

    report.ai_summary = json.dumps(summary, ensure_ascii=False)
    platform.event(s, report, user, 'AI 摘要', '生成核心观点/逻辑链/数据要点摘要卡')
    s.commit()
    return summary
