# 前端（Vue 3 + Element Plus + Vite）

构建产物是纯静态文件：本地由 Vite 前台代理 `/api`，线上由 Nginx 托管 `dist` 并反代 `/api`。

```
index.html            Vite 入口，仅挂载 #app
vite.config.js        dev server + /api 代理（changeOrigin=false，保留原始 Host）
nginx.conf            线上静态页面 + /api 反向代理
Dockerfile            多阶段：node 构建 → nginx 运行
tests/browser_smoke.mjs  真实 Chromium 登录并逐页渲染，收集控制台错误
src/
  main.js             createApp + Element Plus（中文包）+ 路由
  App.vue             根组件
  api/index.js        请求层：同源 Cookie、错误归一
  store/session.js    会话与 /api/state 全量数据（computed 派生）
  utils/format.js     状态口径、角色名、时间、排序
  utils/menu.js       侧边菜单树与面包屑（与操作手册目录一致）
  router/index.js     路由与登录守卫
  layout/AppLayout.vue  侧边栏、顶栏、面包屑、改密与退出
  components/         研报列表、状态徽标、页头、富文本、组件块、新建研报、报告操作
  views/              登录、工作台、研报中心、审核中心、编辑器、资料库、数据中心、
                      分类配置、作者、品种、审批流、部门、角色、基本配置
  styles/index.css    唯一样式表（Element Plus 设计令牌 + 业务样式）
```

## 本地开发

```bash
npm install
npm run dev        # http://127.0.0.1:5173，/api 代理到 127.0.0.1:8080
```

`API_TARGET` 改后端地址，`DEV_PORT` 改页面端口。改文件即时热更新。

后端对所有 POST 校验 `Origin` 与 `Host` 同源，代理必须保留浏览器的原始 Host。Vite 用 `changeOrigin: false` 做到这一点；换成别的代理时请保留原始 Host（或传 `X-Forwarded-Host`），否则登录、保存会返回「跨站请求被拒绝」。

## 构建与部署

```bash
npm run build      # 产出 dist/
```

`Dockerfile` 分两阶段：`node:20-alpine` 跑 `npm run build`，`nginx:stable-alpine` 只拷贝 `dist`。运行镜像不含 node_modules，源码不进入运行容器。

## 冒烟

```bash
npm run smoke      # 默认 http://127.0.0.1:5173
SMOKE_BASE=http://127.0.0.1:8090 npm run smoke   # 指向 python dev.py 的构建产物预览
```

会遍历全部路由，任一页面渲染为空或出现控制台错误即失败。`SMOKE_USER` / `SMOKE_PASS` / `CHROME_PATH` 可覆盖。

模型密钥只放后端环境变量，不要写进本目录。
