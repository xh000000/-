# 期货研究管理平台（前后端分离版）

浏览器界面与业务接口拆成两个独立服务：前端 Vue 3 + Element Plus（构建为静态文件，本地由 Vite 代理、线上由 Nginx 托管），后端 FastAPI + SQLAlchemy + SQLite 提供 API。适用于内部试用，不代表已完成企业生产架构改造。

## 目录与职责

```text
futures-research-separated/
  frontend/
    index.html             Vite 入口（仅挂载 #app）
    package.json           依赖与脚本：npm run dev / build
    vite.config.js         dev server + /api 代理（changeOrigin=false，保留原始 Host）
    nginx.conf             线上静态页面与 /api 反向代理
    Dockerfile             多阶段构建：node 构建 → nginx 托管 dist
    src/
      main.js              createApp + Element Plus（中文包）+ 路由
      App.vue              根组件
      api/index.js         请求层：同源 Cookie、错误归一
      store/session.js     reactive 会话与 /api/state 全量数据
      utils/format.js      状态口径、角色名、时间与排序
      utils/menu.js        侧边菜单树与面包屑（与操作手册目录一致）
      router/index.js      路由与登录守卫
      layout/AppLayout.vue 侧边栏、顶栏、面包屑、改密与退出
      components/          研报列表、状态徽标、页头、富文本、组件块、新建研报、报告操作
      views/               登录、工作台、研报中心、审核中心、编辑器、资料库、数据中心、
                           分类配置、作者、品种、审批流、部门、角色、基本配置
      styles/index.css     唯一权威样式表（Element Plus 设计令牌 + 业务样式）
  backend/
    server.py              启动入口：把 FastAPI 应用交给 uvicorn（保持 python backend/server.py 用法）
    app.py                 FastAPI 应用：路由、依赖注入、会话鉴权、CSRF、异常映射、定时发布
    db.py                  SQLAlchemy 2.0 数据层：18 张表 ORM 映射、引擎与会话工厂、幂等迁移
    requirements.txt       后端依赖（fastapi / uvicorn / sqlalchemy）
    report_engine.py       分类配置、结构化文档、版本与审批流转
    manual_engine.py       分类树、作者/品种、章节协作及访问权限
    library_engine.py      云盘、文档、素材资料与批量操作
    iam_engine.py          账号、部门、角色菜单、审批流、修改密码
    agent/                 Agent 服务层（LangGraph 智能体基座，可选依赖）
      config.py            AGENT_* 独立模型配置，逐项回落平台外部模型
      memory.py            会话记忆（SqliteSaver，独立 agent_memory.db）
      tools.py             平台工具注册表：查研报/指标/品种/资料 + 受限写章节
      graph.py             ReAct 智能体（create_react_agent + 系统提示词）
      service.py           SSE 事件流、对话线程、后台任务队列
      routes.py            /api/agent/* 路由
    printview.py           服务端打印视图（A4 研报版式，浏览器可另存为 PDF）
    richtext.py            富文本 HTML 白名单清洗
    test_agent.py          Agent 服务层测试，不属于运行依赖
    test_workflow.py       后端自动化测试，不属于运行依赖
    Dockerfile             后端镜像
  dev.py                   可选：不装 Node 时预览已构建的 dist（静态 + /api 代理）
  frontend/tests/browser_smoke.mjs  浏览器冒烟：真实 Chromium 登录并逐页渲染、收集控制台错误
  compose.yaml             两个服务的部署编排
  .env.example             模型与 Cookie 环境变量示例
```

前端为 Vue 3 + Element Plus，构建工具 Vite；后端为 FastAPI + SQLAlchemy 2.0，数据库 SQLite。

## 后端技术栈

| 关注点 | 实现 |
| --- | --- |
| HTTP 框架 | FastAPI 0.163（`app.py`），uvicorn 托管，`server.py` 仅作启动入口 |
| 接口文档 | 运行后访问 `/api/docs`（Swagger UI）、`/api/openapi.json`（OpenAPI 3.1） |
| 数据层 | SQLAlchemy 2.0 声明式模型（`db.py`，18 张表）；全部业务查询走 ORM 表达式，无手写 SQL |
| 事务 | 每请求一个 `Session`，端点成功即 `commit`，异常回滚 |
| 鉴权 | PBKDF2 密码哈希 + `sessions` 表令牌 + HttpOnly/SameSite=Strict Cookie |
| 安全 | POST 同源校验（Origin 对 Host / X-Forwarded-Host）、请求体 8MB 上限、富文本白名单 |

**数据层说明**：研报、分类、作者品种、素材库、IAM 五个模块的查询与写入全部使用
SQLAlchemy 表达式（`select` / `insert` / `update`）或模型属性赋值，不再拼裸 SQL；
只有建表与幂等迁移保留 DDL 原文。会话对象在请求生命周期内共享，端点统一在
`app.py` 的依赖里 `commit` / 回滚，业务函数返回 `(payload, status)` 而不自己提交事务。

## 请求路径

- **本地**：`npm run dev` 起 Vite（默认 `127.0.0.1:5173`），页面与 `/api` 代理同源，请求由 Vite 前台代理到本地后端 `127.0.0.1:8080`。改代码即时热更新。
- **线上**：Nginx 托管 `dist` 静态文件，`/api/...` 由 Nginx 反向代理到 `backend:8080`。后端开启 `API_ONLY=1`，只提供 API，两个服务可分别构建和重启，后端不映射宿主机端口。

两种方式浏览器都只访问一个地址，Cookie 登录继续有效，无须放开跨域或把模型密钥交给前端。跨服务器部署时，修改 `frontend/nginx.conf` 的 `proxy_pass` 为实际后端地址，并设置 HTTPS 及适当的网络访问限制。

## 部署（服务器 / Docker）

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

Linux 用 `cp .env.example .env`。打开 http://127.0.0.1:8080 ，首次进入创建管理员（密码至少 6 位）。数据保存在命名卷中。

如果原有一体版占用 8080，先停止它，或把 Compose 中前端端口改成 `127.0.0.1:8090:80`。新 Compose 项目创建新数据卷，现有业务数据不会自动迁入；迁移需停服备份原库后导入新卷。

## 本地开发

本地不走 Nginx，由 Vite 在前台代理。两个终端：

```powershell
# 终端 0：首次安装后端依赖
pip install -r backend/requirements.txt

# 终端 1：后端（FastAPI + uvicorn）
$env:PORT='8080'; python backend/server.py
# 启动后接口文档：http://127.0.0.1:8080/api/docs

# 终端 2：前端（Vite 代理 /api → 127.0.0.1:8080）
cd frontend
npm install          # 首次
npm run dev          # http://127.0.0.1:5173
```

改前端文件即时生效，无需构建。`vite.config.js` 的 `server.proxy` 默认指向 `http://127.0.0.1:8080`，可用 `API_TARGET` 覆盖，`DEV_PORT` 改页面端口。

后端对所有 POST 校验 `Origin` 与 `Host` 同源（CSRF 防护），因此代理必须保留浏览器的原始 `Host`。Vite 的 `changeOrigin: false` 与 Nginx 的 `proxy_set_header Host $http_host` 都是这个作用；若换成别的代理，请同样保留原始 Host（或传 `X-Forwarded-Host`），否则页面能打开但登录、保存会返回「跨站请求被拒绝」。

### 可选：不装 Node 时预览构建产物

`dev.py` 是纯标准库的静态服务器，服务 `frontend/dist` 并把 `/api` 反代到后端，行为与线上 Nginx 一致，适合验证构建结果：

```powershell
cd frontend && npm run build && cd ..
python dev.py --with-backend      # 一条命令：拉起本地后端 + dist + 代理，端口 8090
```

## 构建

```powershell
cd frontend
npm run build        # 产出 frontend/dist
```

`frontend/Dockerfile` 用 `node:20-alpine` 构建、`nginx:stable-alpine` 运行，运行镜像不含 node_modules。

## 测试

```powershell
# 后端：接口、权限、审批流、定时发布、打印视图，使用临时库
python backend/test_workflow.py

# Agent 服务层：状态、线程、SSE 降级、后台任务、工具链路（无需模型密钥）
python backend/test_agent.py

# 前端：真实 Chromium 登录并逐页渲染，收集控制台报错（需前端与后端已启动）
cd frontend && npm run smoke
```

`frontend/tests/browser_smoke.mjs` 使用 `puppeteer-core` 驱动本机 Chrome。默认地址 `http://127.0.0.1:5173`，可用 `SMOKE_BASE`、`SMOKE_USER`、`SMOKE_PASS`、`CHROME_PATH` 覆盖。它会遍历全部路由，任一页面出现控制台错误或渲染为空即失败。

## 权限与状态口径

- 账号：`users` 表保留四种流程角色（研究员 / 研究复核 / 合规审核 / 发布专员）+ 管理员。研报审批链按角色判定，避免自定义角色绕过流程。
- 角色菜单：`roles` 表保存可见菜单集合，登录后 `/api/state` 返回 `user.menus`，侧边栏据此显示；管理员为 `*`。
- 会话：Cookie `research_session_<port>`，`HttpOnly; SameSite=Strict`；勾选「保持登录」有效期 30 天，否则 8 小时且 30 分钟无操作自动失效。改密后旧会话立即失效。
- 列表状态口径（内部值 → 手册用语）：`草稿` → 待提交；`研究复核`、`合规审核` → 待审批；`待发布` → 已通过；`已发布` → 已发布；`已退回` → 已驳回。

## 新增接口

| 接口 | 说明 |
| --- | --- |
| `POST /api/password` | 修改本人密码，注销其他会话 |
| `GET/POST /api/users` | 账号列表、创建、停用、重置密码（管理员） |
| `GET/POST /api/departments` | 部门增删改，最多两级 |
| `GET/POST /api/roles` | 角色与菜单权限，内置角色不可删除 |
| `GET/POST /api/approval-flows` | 审批流独立配置，按分类绑定，支持或签/会签/依次 |
| `POST /api/report-schedule` | 定时发布，仅发布专员与管理员，空值取消 |
| `GET /api/report-print/<id>` | 服务端打印视图（A4 分页），浏览器打印为 PDF |
| `POST /api/report-preview` | 用同一渲染器输出未保存草稿的预览 HTML，供编辑器内嵌 |
| `GET /api/library/zip?ids=` | 资料批量打包下载 |
| `POST /api/library/batch` | 资料批量移动 / 删除 |

定时发布由后端守护线程每 30 秒扫描一次：`待发布` 且 `scheduled_at` 到期的报告自动置为 `已发布`，并写入操作留痕。

## 研报章节与版式（对齐《兴业期货日度策略》）

章节结构与打印版式取自《兴业期货日度策略》合集（11 月 12 期格式稳定），不再使用通用占位标题：

| 层级 | 内容 |
| --- | --- |
| 一级 | 一、重点策略推荐 ｜ 二、宏观资讯速递 ｜ 三、金融与商品基本面展望 ｜ 四、数据来源与免责声明 |
| 二级 | 01 宏观要闻 / 02 行业要闻 / 03 财经日历；01 金融衍生品 … 06 农产品；01 数据来源与风险提示 |

- **添加研报**：对话框内直接展示本次将生成的章节结构（一级分组 + 二级编号 + 该板块覆盖的合约代码），标题按 `兴业期货日度策略（{日期点分}）` 自动生成，可修改。
- **编辑器**：左侧章节按一级分组、二级编号排列；章节画布上显示「关联品种」标签（如 `铜 CU`、`铁矿石 I`）；空章节给出该板块的品种骨架（如 `▍铜：`、`▍豆粕：`），可一键插入后逐段填写。
- **预览与打印**：编辑器「预览」直接内嵌 `POST /api/report-preview` 的渲染结果，与「打印 / PDF」是同一份 HTML、同一套 CSS，因此两处版式必然一致。版式为：首页深蓝品牌条 + 浅蓝标题带，内页小标页眉 + 蓝色细分隔线，每页深蓝页脚带「请务必阅读正文之后的免责条款部分」与页码；一级章节 14pt 蓝色、二级板块 12pt 黑色编号、正文宋体 10.6pt 首行缩进两字两端对齐、`▍品种：观点` 整行加粗；尾页依次为数据来源（灰）、（以上内容仅供参考…）、投资咨询部色带与资格证号两列、作者承诺色带、免责声明色带。
- **分页**：渲染结果内嵌一段按 A4 实测高度切页的脚本（页边距 31.8mm、正文宽 146.5mm、页脚 10mm），色带与其后正文绑定在同一页，标题不会落在页脚。
- **配置入口**：`分类配置 → 章节结构` 可调整一级章节（`group`）、编号（`label`）与各章关联品种（按板块勾选）；`版式与品牌` 可改版头、作者承诺、免责声明与联系电话；`作者管理` 增加资格证号，打印时随署名输出。
- **存量数据**：服务启动时执行两个一次性升级——`daily-template-v1` 把历史「品种日报」换成日度策略章节，`daily-paper-v2` 把混在一起的版尾拆成「作者承诺」与「免责声明」；只影响之后新建的报告，已有报告沿用创建时的配置快照。

### 期货品种库

`品种管理` 为两级结构「板块 → 期货品种（含合约代码）」，与合集「三、金融与商品基本面展望」的 01～06 一一对应（`schema_flags = commodity-tree-v1`，幂等）：

| 板块 | 期货品种（合约代码） |
| --- | --- |
| 金融衍生品 | 股指 IF/IH/IC/IM ｜ 国债 T/TF/TS/TL |
| 贵金属 | 黄金 AU ｜ 白银 AG |
| 有色与新能源 | 铜 CU ｜ 铝 AL ｜ 氧化铝 AO ｜ 镍 NI ｜ 工业硅 SI ｜ 多晶硅 PS |
| 黑色建材 | 螺纹钢 RB ｜ 热卷 HC ｜ 铁矿石 I ｜ 焦煤 JM ｜ 焦炭 J ｜ 纯碱 SA ｜ 玻璃 FG |
| 能源化工 | 原油 SC ｜ 甲醇 MA ｜ PVC V |
| 农产品 | 棕榈油 P ｜ 豆油 Y ｜ 菜籽油 OI ｜ 豆粕 M ｜ 棉花 CF ｜ 白糖 SR |

日度策略各板块章节的 `commodity_ids` 由该表自动写入，新建报告时带到章节上；`综合` 保留为综合研究题材。品种改名或停用后，历史报告的关联以创建时的标识为准。

## Agent 服务层（LangGraph 智能体基座）

后端在业务引擎之上新增一层 Agent 服务：LangGraph ReAct 智能体可以调用平台工具
（查研报、读章节、查指标序列、查品种库、搜资料库），并把候选章节草稿写回平台——
写操作复用 `/api/chapter/save` 的全部校验链（权限、版本快照、操作留痕），
内容始终是「候选草稿」，必须人工核对后才能送审。

```text
backend/agent/
  config.py   模型配置：AGENT_* 环境变量优先，未配置的项逐项回落页面外部模型（AI_*）
  memory.py   会话记忆：LangGraph SqliteSaver，独立文件 agent_memory.db（不混业务库）
  tools.py    工具注册表：新工具在 _registry 加一行，状态页清单自动更新
  graph.py    智能体：create_react_agent + 按用户/日期动态生成的系统提示词
  service.py  SSE 事件流（token/工具调用/结果）、线程管理、单 worker 后台任务队列
  pipeline.py AI 日报流水线：取数 → 逐板块写稿 → 自动建报告 → 送研究复核
  summarize.py 研报 AI 秒读：核心观点/逻辑链/数据要点三段式摘要卡
  routes.py   REST + SSE 路由，复用平台 Cookie 会话与 CSRF 校验
```

依赖为可选：`requirements.txt` 里 langchain 系列未安装时，启动日志会提示
`agent layer disabled`，平台以无 Agent 模式运行，其余功能不受影响。
langchain 导入全部惰性化，`import app` 保持秒级，定时任务等子进程不受拖累。

### 配置

`.env`（参考 `.env.example`）：

| 变量 | 说明 |
| --- | --- |
| `AGENT_API_KEY` / `AGENT_MODEL` / `AGENT_BASE_URL` | Agent 专用模型，逐项独立生效；某项未配置时回落到平台外部模型，都不配则 Agent 不可用 |
| `AGENT_MAX_TOKENS` / `AGENT_TEMPERATURE` / `AGENT_TIMEOUT` | 单次输出上限、采样温度、调用超时 |
| `AGENT_RECURSION_LIMIT` | 单轮对话最多工具调用循环数（默认 40） |
| `AGENT_PIPELINE_TIME` | AI 日报定时触发（UTC HH:MM）；留空则只在页面手动触发，每天最多自动跑一次 |

### API（全部要求登录）

| 接口 | 说明 |
| --- | --- |
| `GET /api/agent/status` | 是否已配置、模型出处、工具清单 |
| `GET/POST/DELETE /api/agent/threads` | 对话线程管理（消息记忆随线程保存，删除连带清记忆） |
| `GET /api/agent/threads/{id}/messages` | 回放历史消息 |
| `POST /api/agent/chat` | SSE 流式对话：`start` / `token` / `tool_start` / `tool_end` / `done` / `error` 事件 |
| `POST /api/agent/tasks` | 投递后台任务（单 worker 顺序执行），`GET /api/agent/tasks/{id}` 轮询结果 |
| `POST /api/agent/pipeline/run` | 触发 AI 日报流水线（后台执行，结果摘要含报告 id 与各章节状态） |
| `POST /api/agent/summary` | 为研报生成三段式 AI 摘要卡（写进 `reports.ai_summary`，列表随 to_dict 带出） |

### 安全与合规约束

- 工具按当前登录用户构建：读工具走 `manual.can_view` 口径，看不见的报告读不到；
  写工具仅限草稿/已退回状态、本人可编辑的章节。
- 系统提示词写死行为规则：数据必须来自工具返回的真实数据并注明来源与日期；
  禁止「保本、稳赚、保证收益、必涨、必跌」类表述；观点必须附风险提示。
- Agent 不能提交、审批、发布——流程决定权始终在人。
- Agent 产出的报告自动打上 `ai_draft=1` 标记：研报列表显示「AI 初稿」徽标，
  并追加 `AI 初稿` 留痕事件；AI 日报流水线生成的报告只会推进到「研究复核」，
  复核 → 合规 → 发布必须由对应角色人工操作（见 `reports.ai_draft` 列）。

### 前端（AI 问答）

侧边菜单「工具箱 → AI问答」（`/agent`）即对话界面：左侧对话线程列表（新建 / 切换 / 删除，删除连带清记忆），
右侧消息区流式渲染（token 增量、工具调用徽标、停止按钮），未配置模型时显示引导提示而非空壳。
对话请求走 `POST /api/agent/chat` 的 SSE 流，`Ctrl+Enter` 发送；浏览器冒烟已覆盖该页面。
页头「AI 日报」按钮一键触发流水线：自动取数、逐板块生成初稿、创建报告并推进到研究复核，
完成后弹窗汇报章节撰写情况（对标同业「分钟级初稿 + 研究员复核」模式）。

## 观点库与准确率回溯（对标 ETA 观点考核 / 中泰后台）

`backend/viewpoint.py`（路由 `/api/viewpoints/*`，纯业务模块，无 langchain 依赖）：

- **登记观点**：品种、方向（看多/看空/震荡）、依据、观察期（1~90 自然日）；
  基准价自动取指标库最新价（优先级：现货价 → 收盘价 → 结算价 → 最新点位），也可手工填写；
- **自动回溯**：到期后取同一指标在结算日前最近的价格，对照基准价算区间涨跌幅，
  按 ±1% 阈值判「正确 / 错误 / 持平」，无价格数据标「无法结算」——绝不编造结果；
  访问列表时自动结算到期观点，也可提前手动结算；
- **画像**：按观点人、按品种统计正确率与方向分布（`GET /api/viewpoints/stats`）。

前端菜单「研报管理 → 观点库」（`/viewpoints`）：整体正确率卡片、筛选表格、
研究员画像与品种正确率两块面板、登记观点弹窗。

## 数据录入增强（对标 ETA 数据报表管理）

- **数据源巡检看板**：`GET /api/data/sources` 额外返回 `health`——每来源近 30 天
  同步成功率、最近成功时间、滞后指标数（最新数据距今 > 3 天）、异常配置数，
  前端按红/黄/绿三档展示；
- **新鲜度**：`stats()` 带每来源 `stale_days` 与 `late_indicators`，
  指标目录（`catalog()`）每行带 `stale_days`/`stale`，来源卡片显示「滞后 X 天」；
- **失败排查**：同步作业与取数配置失败时自动分类原因（凭据/鉴权、接口限流、
  参数/指标编码、网络/超时），详情弹窗给出对应排查步骤清单。

## 与操作手册的差距

本轮已补齐研报主线闭环：修改密码、角色菜单权限、部门与账号管理、审批流独立配置、研报状态与列表操作口径、定时发布、打印视图与 PDF 导出、素材库三级分类及批量打包。手册中 BI 看板、智能 PPT、指标库、AI 预测模型、量化策略、图库、表格、逻辑图、语义分析、统计分析、供应分析、工具箱、数据报表管理等模块尚未接入，侧边栏按手册保留位置并标注「未接入」，不提供空壳页面。

已知限制：长图导出未实现。现有替代方案是服务端打印视图，浏览器「打印 → 另存为 PDF」可得到 PDF；长图需引入前端截图库或后端无头浏览器，属于新增依赖，未在本轮加入。

数据接入分三条通道，共用同一套校验与幂等规则（同来源+指标+日期唯一，重复同步不产生重复行）：

1. **服务端直连**（推荐）：「数据源 → 手工数据录入 → 取数配置」填接口地址、账号密钥、同步范围与执行计划，服务端点「执行」或到点自动取数入库。同花顺 iFinD 走内置预设（access_token + 历史行情），其他厂商选「通用 JSON 接口」，用 `{code}` `{metric}` `{startdate}` `{enddate}` 占位拼请求，再指定响应里的数组路径与日期/数值字段即可。
2. **连接器回填**：页面登记同步范围，由已授权通道（WorkBuddy 连接器 / 数据管理员）取数后经 `backend/sync_worker.py` 回填。
3. **CSV 导入**：备用通道。

数据来源本身也是数据（`data_sources` 表）：以后接卓创、钢联等厂商，在页面上「添加数据来源」即可，不用改代码；同步记录可按来源、状态、关键字与日期查询并看明细。入库后可在「数据源 → 指标查询」按来源与名称检索指标，查看区间统计、走势与逐日明细。外部模型按 `.env.example` 配置：默认走 OpenAI 兼容接口；若只有 CodeBuddy 的密钥，设 `AI_PROVIDER=codebuddy-cli` 改由本机 `codebuddy -p` 调用（该密钥无官方 OpenAI 兼容端点）。管理员也可在「系统设置 → 基本配置 → 外部模型」里直接选模型、填接口地址与密钥：设置存进数据库、优先于环境变量，保存即生效无需重启；密钥只回显掩码，不下发浏览器。生成内容为候选草稿，必须人工核对后保存。
