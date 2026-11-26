"""Agent 独立模型配置：与页面「外部模型」分开选型、分开计费。

优先级（每项独立判断）
--------------------
1. 环境变量 AGENT_BASE_URL / AGENT_API_KEY / AGENT_MODEL；
2. 某项未配置时回落到平台外部模型（app_settings 里的 ai_* 或 AI_* 环境变量），
   回落值由调用方传入（routes.py 从 app 层取），本模块不反向依赖 app。
调参项（max_tokens / temperature / timeout / recursion_limit）只认环境变量。
"""
from __future__ import annotations

import os


def _env(name: str, default: str = '') -> str:
    return (os.getenv(name) or default).strip()


def resolve(fallback: dict | None = None) -> dict:
    """合并 AGENT_* 环境变量与回落配置，返回完整模型参数。"""
    fb = fallback or {}
    return {
        'base_url': _env('AGENT_BASE_URL') or str(fb.get('base_url') or '').rstrip('/'),
        'api_key': _env('AGENT_API_KEY') or str(fb.get('api_key') or ''),
        'model': _env('AGENT_MODEL') or str(fb.get('model') or ''),
        'max_tokens': int(_env('AGENT_MAX_TOKENS', '8000') or '8000'),
        'temperature': float(_env('AGENT_TEMPERATURE', '0.3') or '0.3'),
        'timeout': int(_env('AGENT_TIMEOUT', '180') or '180'),
        'recursion_limit': int(_env('AGENT_RECURSION_LIMIT', '40') or '40'),
    }


def ready(cfg: dict) -> bool:
    """密钥和模型名齐了才算可用；base_url 缺省时 langchain-openai 会走官方端点。"""
    return bool(cfg['api_key'] and cfg['model'])


_LABELS = {'model': '模型', 'base_url': '接口地址', 'api_key': '密钥'}


def source_of(cfg: dict, fallback: dict | None = None) -> str:
    """给状态页说明每个配置项的出处，管理员排查时不用翻 .env。"""
    fb = fallback or {}
    parts = []
    for key, env in [('model', 'AGENT_MODEL'), ('base_url', 'AGENT_BASE_URL'), ('api_key', 'AGENT_API_KEY')]:
        if (os.getenv(env) or '').strip():
            parts.append('%s（环境变量 %s）' % (_LABELS[key], env))
        elif fb.get(key):
            parts.append(_LABELS[key] + '（回落平台外部模型）')
        else:
            parts.append(_LABELS[key] + '（未配置）')
    return '；'.join(parts)
