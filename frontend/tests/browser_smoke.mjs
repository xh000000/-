/**
 * 浏览器冒烟：真实 Chromium 登录后逐页渲染，收集控制台错误与未捕获异常。
 *
 * 前置（本地开发形态：Vite 前台代理 /api → 后端）：
 *   python backend/server.py            # 终端 1，默认 8080
 *   cd frontend && npm run dev          # 终端 2，默认 5173
 *   node tests/browser_smoke.mjs        # 终端 3
 *
 * 也可指向构建产物（python dev.py --with-backend，端口 8090）：
 *   SMOKE_BASE=http://127.0.0.1:8090 node tests/browser_smoke.mjs
 *
 * 环境变量：SMOKE_BASE / SMOKE_USER / SMOKE_PASS / CHROME_PATH / SMOKE_HEADFUL=1
 */
import { existsSync } from 'node:fs';
import puppeteer from 'puppeteer-core';

const BASE = (process.env.SMOKE_BASE || 'http://127.0.0.1:5173').replace(/\/$/, '');
const USER = process.env.SMOKE_USER || 'admin';
const PASS = process.env.SMOKE_PASS || 'admin888';

const CANDIDATES = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
].filter(Boolean);

const ROUTES = [
  ['/', '工作台'],
  ['/agent', 'AI 问答'],
  ['/reports', '研报中心'],
  ['/viewpoints', '观点库'],
  ['/approval', '审核中心'],
  ['/library/cloud', '云盘'],
  ['/library/docs', '文档管理库'],
  ['/library/materials', '素材库'],
  ['/data', '数据录入'],
  ['/data/indicators', '指标查询'],
  ['/config/categories', '研报分类树'],
  ['/config/authors', '作者管理'],
  ['/config/commodities', '品种管理'],
  ['/config/flows', '审批流设置'],
  ['/system/departments', '部门管理'],
  ['/system/users', '账号管理'],
  ['/system/roles', '角色管理'],
  ['/system/models', '外部模型'],
];

const NOISE = [
  /favicon/i,
  /Download the Vue Devtools/i,
  /\[vite\] connect/i,
];

const executablePath = CANDIDATES.find(path => existsSync(path));
if (!executablePath) {
  console.error('未找到 Chrome/Edge，可设置 CHROME_PATH 指向可执行文件');
  process.exit(2);
}

const failures = [];

async function login(page) {
  await page.goto(BASE + '/login', { waitUntil: 'networkidle2', timeout: 30000 });
  await page.waitForSelector('.login-card input', { timeout: 15000 });
  const inputs = await page.$$('.login-card input');
  await inputs[0].type(USER, { delay: 8 });
  const password = await page.$('.login-card input[type="password"]');
  await password.type(PASS, { delay: 8 });
  await page.click('.login-card button.submit');
  await page.waitForSelector('.app-shell', { timeout: 20000 });
}

const browser = await puppeteer.launch({
  executablePath,
  headless: process.env.SMOKE_HEADFUL === '1' ? false : true,
  args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--window-size=1440,900'],
  defaultViewport: { width: 1440, height: 900 },
});

try {
  const page = await browser.newPage();
  let scope = '初始化';
  const problems = [];

  page.on('console', message => {
    if (message.type() !== 'error' && message.type() !== 'warning') return;
    const text = (message.text() || '') + ' ' + (message.location()?.url || '');
    if (NOISE.some(pattern => pattern.test(text))) return;
    if (message.type() === 'warning' && !/Vue warn/i.test(text)) return;
    // 登录前访问 /api/state 会返回 401，是正常流程（未登录），不计入问题
    if (scope === '初始化' && /401/.test(text)) return;
    problems.push(`[${scope}] console.${message.type()}: ${text.slice(0, 300)}`);
  });
  page.on('pageerror', error => {
    problems.push(`[${scope}] pageerror: ${String(error.message || error).slice(0, 300)}`);
  });

  await login(page);
  console.log('ok   登录 ' + BASE);

  for (const [path, title] of ROUTES) {
    scope = title;
    const before = problems.length;
    await page.goto(BASE + path, { waitUntil: 'domcontentloaded', timeout: 30000 });
    let textLength = 0;
    try {
      await page.waitForFunction(
        () => {
          const main = document.querySelector('.app-main');
          return main && (main.innerText || '').trim().length > 40;
        },
        { timeout: 15000 }
      );
      textLength = await page.evaluate(
        () => (document.querySelector('.app-main')?.innerText || '').trim().length
      );
    } catch {
      textLength = 0;
    }

    const heading = await page.evaluate(
      () => document.querySelector('.page-head h2')?.innerText?.trim() || ''
    );
    const crashed = problems.length > before;
    if (!textLength || crashed) {
      failures.push({ path, title, textLength, heading });
      console.log(`FAIL ${title.padEnd(8)} ${path}  渲染 ${textLength} 字符${crashed ? '（有控制台错误）' : ''}`);
    } else {
      console.log(`ok   ${title.padEnd(8)} ${path}  ${String(textLength).padStart(5)} 字符  ${heading}`);
    }
  }

  /* 弹窗类交互：只断言"页面渲染通过"抓不到未声明的 ref ——
     按钮点了不报错、也没反应（Vue 只在控制台提示一次），必须真的点开看内容。 */
  scope = '交互';
  const beforeActions = problems.length;
  await page.goto(BASE + '/reports', { waitUntil: 'domcontentloaded', timeout: 30000 });
  // 列表是异步拉取的，先等首行出现再点，否则会误判为"库里没有研报"
  await page
    .waitForFunction(() => document.querySelector('.el-table__body tbody tr td button.title-link'), { timeout: 15000 })
    .catch(() => {});
  const entered = await page.evaluate(() => {
    const link = document.querySelector('.el-table__body tbody tr td button.title-link');
    if (!link) return false;
    link.click();
    return true;
  });

  if (!entered) {
    console.log('skip 交互检查  库里没有研报，无法验证编辑器弹窗');
  } else {
    await page.waitForFunction(() => document.querySelector('.edit-top .actions button'), { timeout: 20000 });
    await new Promise(resolve => setTimeout(resolve, 800));

    /* 列表点标题现在先进只读详情（?mode=view），详情里确认没有编辑工具条，
       再点「编辑研报」进入编辑态，后面的编辑器弹窗仍按原路径验证。 */
    const detail = await page.evaluate(() => ({
      view: new URLSearchParams(location.search).get('mode') === 'view',
      title: !!document.querySelector('.detail-title'),
      insertButtons: [...document.querySelectorAll('.chapter-toolbar button')].length,
    }));
    const editable = await page.evaluate(() => {
      const button = [...document.querySelectorAll('.edit-top .actions button')].find(el => el.innerText.trim() === '编辑研报');
      if (!button) return false;
      button.click();
      return true;
    });
    if (editable) {
      await page.waitForFunction(() => document.querySelector('.title-input'), { timeout: 10000 });
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    console.log(`${detail.view && detail.title && !detail.insertButtons ? 'ok   ' : 'FAIL '}详情只读    ${detail.view ? '?mode=view' : '缺 mode'} / ${detail.title ? '标题为静态' : '标题仍是输入框'} / 插入按钮 ${detail.insertButtons} 个`);
    if (!editable) console.log('skip 编辑态   该报告当前不可编辑，跳过编辑器弹窗');

    const openDialog = async label => {
      // 详情态叫「报告信息」，编辑态叫「基础信息」，两个都认
      const labels = label === '基础信息' ? ['基础信息', '报告信息'] : [label];
      const clicked = await page.evaluate(texts => {
        const buttons = [...document.querySelectorAll('.edit-top .actions button')];
        const btn = texts.map(text => buttons.find(el => el.innerText.trim() === text)).find(Boolean);
        if (!btn) return false;
        btn.click();
        return true;
      }, labels);
      if (!clicked) return { ok: false, reason: '工具栏无此按钮' };
      try {
        await page.waitForFunction(
          () => {
            const dialog = [...document.querySelectorAll('.el-dialog')].find(el => {
              const overlay = el.closest('.el-overlay');
              return overlay && getComputedStyle(overlay).display !== 'none';
            });
            return dialog && (dialog.innerText || '').trim().length > 20;
          },
          { timeout: 8000 }
        );
      } catch {
        return { ok: false, reason: '弹窗未出现或内容为空' };
      }
      const info = await page.evaluate(() => {
        const dialog = [...document.querySelectorAll('.el-dialog')].find(el => {
          const overlay = el.closest('.el-overlay');
          return overlay && getComputedStyle(overlay).display !== 'none';
        });
        return {
          title: dialog.querySelector('.el-dialog__title')?.innerText?.trim() || '',
          length: (dialog.innerText || '').trim().length,
        };
      });
      await page.keyboard.press('Escape');
      // 等遮罩真正消失再继续：Element 的关闭有 300ms 过渡，抢在过渡里点下一个按钮
      // 会点到上一个弹窗，后续断言全部错位。
      await page.waitForFunction(
        () => [...document.querySelectorAll('.el-overlay')].every(el => getComputedStyle(el).display === 'none'),
        { timeout: 5000 }
      ).catch(() => {});
      await new Promise(resolve => setTimeout(resolve, 150));
      return { ok: true, ...info };
    };

    for (const label of ['基础信息', '预览']) {
      const result = await openDialog(label);
      if (result.ok) {
        console.log(`ok   弹窗 ${label.padEnd(6)} ${result.title}  ${result.length} 字符`);
      } else {
        console.log(`FAIL 弹窗 ${label.padEnd(6)} ${result.reason}`);
        failures.push({ path: '/reports/' + '(编辑器)', title: '弹窗 ' + label, textLength: 0, heading: '' });
      }
    }

    /* 预览改为内嵌渲染（与打印同一份 HTML）：必须真的切出 A4 页，只检查弹窗文字抓不到渲染失败。 */
    await page.evaluate(() => {
      [...document.querySelectorAll('.edit-top .actions button')].find(el => el.innerText.trim() === '预览')?.click();
    });
    await page.waitForFunction(() => !!document.querySelector('.preview-frame iframe'), { timeout: 15000 }).catch(() => {});
    await new Promise(resolve => setTimeout(resolve, 1200));
    const previewFrame = page.frames().find(frame => frame !== page.mainFrame());
    /*
     * 分页是 iframe 内的异步过程：先有 1 页，再逐节点搬运正文。只等待「页数 > 0」
     * 会在切分开始前就返回，把 5 页的稿子误判成 1 页。这里连续采样到页数稳定再判定。
     */
    let previewInfo = { count: 0, chars: 0 };
    let lastCount = -1;
    let stableRounds = 0;
    for (let i = 0; i < 40 && previewFrame; i++) {
      await new Promise(resolve => setTimeout(resolve, 250));
      previewInfo = await previewFrame.evaluate(() => {
        const pages = [...document.querySelectorAll('.page')];
        return {
          count: pages.length,
          chars: pages.reduce((n, p) => n + (p.innerText || '').replace(/\s+/g, '').length, 0),
        };
      }).catch(() => ({ count: 0, chars: 0 }));
      if (previewInfo.count === lastCount) {
        stableRounds += 1;
        if (stableRounds >= 3 && previewInfo.count > 0) break;
      } else {
        stableRounds = 0;
        lastCount = previewInfo.count;
      }
    }
    // A4 一页正文约 1500 字上限；只有 1 页却塞进更多字，说明切分脚本没跑完
    const overflowSinglePage = previewInfo.count === 1 && previewInfo.chars > 1800;
    if (previewInfo.count > 0 && previewInfo.chars > 100 && !overflowSinglePage) {
      console.log('ok   预览分页  ' + previewInfo.count + ' 页 / ' + previewInfo.chars + ' 字');
    } else {
      const reason = overflowSinglePage
        ? '单页塞入 ' + previewInfo.chars + ' 字，分页未生效'
        : '未渲染出 A4 页面';
      console.log('FAIL 预览分页  ' + reason);
      failures.push({ path: '/api/report-preview', title: '预览分页', textLength: previewInfo.chars, heading: '' });
    }
    await page.keyboard.press('Escape');
    await new Promise(resolve => setTimeout(resolve, 300));

    const printTab = new Promise(resolve => browser.once('targetcreated', target => resolve(target)));
    await page.evaluate(() => {
      [...document.querySelectorAll('.edit-top .actions button')].find(el => el.innerText.trim() === '打印 / PDF')?.click();
    });
    try {
      const target = await printTab;
      const tab = await target.page();
      await new Promise(resolve => setTimeout(resolve, 900));
      const printed = await tab.evaluate(() => (document.body.innerText || '').trim().length);
      await tab.close();
      if (printed > 20) {
        console.log(`ok   打印视图  ${printed} 字符`);
      } else {
        console.log('FAIL 打印视图  内容为空');
        failures.push({ path: '/api/report-print', title: '打印视图', textLength: 0, heading: '' });
      }
    } catch {
      console.log('FAIL 打印视图  未打开新标签页');
      failures.push({ path: '/api/report-print', title: '打印视图', textLength: 0, heading: '' });
    }

    if (problems.length > beforeActions) {
      failures.push({ path: '(交互)', title: '交互过程报错' });
    }
  }

  console.log('\n控制台问题：' + (problems.length ? '' : '无'));
  problems.forEach(item => console.log('  ' + item));
  if (problems.length) failures.push({ path: '(console)', title: '控制台' });
} finally {
  await browser.close();
}

if (failures.length) {
  console.error(`\n冒烟失败 ${failures.length} 项`);
  process.exit(1);
}
console.log('\n全部页面渲染通过，失败 0 项');
