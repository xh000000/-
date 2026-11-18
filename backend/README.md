# 后端文件

Python 3.10+，运行时无需第三方包。职责如下：

- `server.py`：API 入口、登录会话、路由、定时发布线程、打印视图与打包下载。
- `report_engine.py`：报告配置、结构化文档、版本、审批。
- `manual_engine.py`：基础资料、章节协作、权限、分类树。
- `library_engine.py`：云盘 / 文档库 / 素材库，批量移动删除与三级分类限制。
- `iam_engine.py`：账号、部门、角色菜单、审批流配置、修改密码。
- `printview.py`：整篇研报的服务端打印视图（浏览器另存为 PDF）。
- `richtext.py`：富文本清洗。
- `test_workflow.py`：业务测试，5 个用例覆盖接口、权限、审批流、定时发布与打印。

PowerShell 本地启动：

```powershell
$env:API_ONLY='1'
python server.py
```

此时 `http://127.0.0.1:8080/api/bootstrap` 返回初始化状态，根路径不提供页面（页面由前端服务提供，开发时用根目录 `dev.py`）。业务数据默认保存在本目录 `data`，可用 `DATA_DIR` 更换；数据库启用 WAL 与忙等超时，避免定时发布线程与请求线程互相阻塞。

数据来源与同步：`datasource.py` 负责幂等入库（`observations` 按 source+indicator+date 唯一）、来源统计与同步作业（表 `data_sync_jobs`）。同花顺 / Wind 的账号凭据由 WorkBuddy 连接器托管，服务端不保存，因此「取数」与「入库」分离：页面 `POST /api/data/jobs` 只登记范围，`sync_worker.py list` 打印待执行作业，`sync_worker.py push <job_id> rows.json` 回填入库，`sync_worker.py fail <job_id> "原因"` 记录取数失败（例如额度用尽）。
服务端直连取数在 `feeds.py`：`data_source_configs` 存接口地址、凭据与计划，`data_sources` 存来源清单（内置同花顺 / Wind，页面可再加）。执行路径是「按品种×指标请求上游 → 解析成观测行 → `datasource.apply` 幂等入库 → 写 `data_sync_jobs`」，定时任务挂在同一个 30 秒调度线程里（`freq=manual/daily/weekly` + `run_at`，当天不重复跑）。两种取数方式：`generic_json` 用占位模板 + 响应路径；`ifind_http` 是 iFinD 预设（`options.field_map` 可改字段名）。凭据只存库、只回掩码，报错落库前会把密钥替换成 `***`；数据库文件需按机密文件保护。接口：`GET/POST /api/data/sources`、`POST /api/data/sources/delete`、`POST /api/data/configs`、`/configs/delete`、`/configs/test`、`/configs/run`、`GET /api/data/jobs`（来源/状态/关键字/日期 + 分页）。

入库后的查询走 `GET /api/data/indicators`（按来源 + 指标 + 单位归拢，带起止日期、首末值与区间涨跌）与 `GET /api/data/series`（单条指标的连续序列，支持 `start` / `end` 日期区间，返回区间统计）。`source` 参数兼容中文名与 key（同花顺 / ifind）。服务端接入新通道（WindPy / iFinD API）时只需产出 `source,indicator,date,value,unit` 行，无需改库与页面。

模型设置使用 `AI_BASE_URL`、`AI_API_KEY`、`AI_MODEL` 环境变量，不在此包包含真实密钥。管理员也可在「基本配置 → 外部模型」里改模型、接口地址和密钥：值存于 `app_settings` 表（键 `ai_model` / `ai_base_url` / `ai_api_key`），优先于环境变量，保存即生效；接口只返回掩码（`sk-d******451e`），明文不出服务端。若使用 CodeBuddy 的密钥，设 `AI_PROVIDER=codebuddy-cli`：该密钥只对 CLI 有效、官方没有 OpenAI 兼容端点，后端会以本机 `codebuddy -p` 子进程调用（`CODEBUDDY_CLI` 可指定可执行文件路径，`CODEBUDDY_INTERNET_ENVIRONMENT=internal` 对应中国版）。两条通道都由服务端发起、密钥不下发前端，生成结果一律是候选草稿，需人工核对。配置页的「测试连接」（`POST /api/ai/test`，仅管理员）会用表单里的地址/密钥/模型真打一次上游，成功顺带回填可用模型列表；列表只缓存在进程内（键含地址与密钥指纹），读取配置不再阻塞打上游。

`/api/generate` 的生成粒度是**单个章节**：证据按该章关联的品种名/合约代码从观测表过滤（匹配不到才退回最近数据），提示词要求只写本章、不复述标题、不套用全文五段式模板。推理模型（如 `deepseek-v4-pro`）的思考 token 与正文共用 `AI_MAX_TOKENS`（默认 8000）；额度被打满时 `finish_reason=length` 且正文为空，后端会自动加倍重试一次（上限 16000），仍失败则返回明确错误而不是空稿。Cookie 的 `Secure` 标记由 `COOKIE_SECURE=1` 打开，只在 HTTPS 下启用。前端经 Nginx 同源代理 `/api/` 访问后端。

测试命令：

```powershell
python test_workflow.py                   # 自建临时库，直接运行
python -m unittest -v test_workflow.py    # 走 unittest 输出
```

Docker 镜像默认设置 `API_ONLY=1`，带 healthcheck，可按完整包中的 Compose 配置运行。
