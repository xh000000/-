/* 应用外壳：登录 → 侧边栏/顶栏 → 页面路由。所有页面按 key 注册在 pages/index.js。 */
import { api, refresh, S, can } from './api.js';
import { esc, ROLE_NAMES, toast, run, modal, closeModal, formObject, STATUS_TEXT } from './ui.js';
import { MENU, breadcrumb, iconSVG } from './menu.js';
import { actions } from './actions.js';
import { PAGES } from '../pages/index.js';

let current = '工作台';
const expanded = new Set(['研报管理', '系统设置']);

export function go(key) {
  const page = PAGES[key];
  if (!page) {
    toast('「' + key + '」尚未接入');
    return;
  }
  const guard = PAGES[current]?.guard?.();
  if (current !== key && guard) {
    toast(guard);
    return;
  }
  current = key;
  const group = groupOf(key);
  if (group) expanded.add(group.label);
  paint();
}

export function page() {
  return current;
}

function leafVisible(item) {
  if (item.admin && S().user.role !== 'admin') return false;
  if (!item.target) return true;
  return can(item.target) || S().user.role === 'admin';
}

function groupOf(key) {
  return MENU.find(item => item.children?.some(child => child.target === key));
}

function sidebarHTML() {
  const leaf = (item, child = false) => {
    const ready = Boolean(PAGES[item.target]) && leafVisible(item);
    const active = ready && current === item.target;
    const note = item.note || (PAGES[item.target] ? '' : '该模块尚未接入，暂不提供入口');
    return `<button type="button" class="menu-leaf${child ? ' nav-child' : ''}${active ? ' active' : ''}" ${ready ? `data-go="${esc(item.target)}"${active ? ' aria-current="page"' : ''}` : 'disabled aria-disabled="true"'} title="${esc(note)}"><span class="menu-name">${esc(item.label)}</span></button>`;
  };
  return MENU.filter(item => !item.admin || S().user.role === 'admin').map((item, index) => {
    if (!item.children) {
      return `<div class="menu-single"><span class="menu-icon">${iconSVG(item.icon)}</span>${leaf(item)}</div>`;
    }
    const children = item.children.filter(leafVisible);
    if (!children.length) return '';
    const open = expanded.has(item.label);
    const contains = children.some(x => x.target === current);
    return `<section class="menu-section"><button type="button" class="menu-toggle${contains ? ' contains-active' : ''}" data-group="${index}" aria-expanded="${open}"><span class="menu-icon">${iconSVG(item.icon)}</span><span class="menu-name">${esc(item.label)}</span><span class="menu-chevron">›</span></button><div class="menu-children" ${open ? '' : 'hidden'}>${children.map(x => leaf(x, true)).join('')}</div></section>`;
  }).join('');
}

const crumbHTML = key => {
  const parts = breadcrumb(key).split(' / ');
  if (parts.length === 1) return `<b>${esc(parts[0])}</b>`;
  return `${esc(parts.slice(0, -1).join(' / '))}<span class="crumb-sep">/</span><b>${esc(parts[parts.length - 1])}</b>`;
};

function paint() {
  const user = S().user;
  document.body.classList.toggle('editing', Boolean(PAGES[current]?.active?.()));
  const initial = String(user.name || '研').slice(0, 1);
  document.getElementById('app').innerHTML = `<aside class="manual-sidebar"><div class="sidebar-brand"><span class="brand-mark">研</span><div class="brand-text"><h2>研枢</h2><small>投研平台</small></div></div><nav id="sidebar-nav" aria-label="主导航">${sidebarHTML()}</nav><div class="sidebar-foot"><b>${esc(user.name)} · ${esc(ROLE_NAMES[user.role] || user.role)}</b>本地部署 · 数据留痕</div></aside>
    <main><header><h1>${crumbHTML(current)}</h1><div class="row topbar"><span class="user-chip"><i>${esc(initial)}</i>${esc(user.name)}<em>${esc(ROLE_NAMES[user.role] || user.role)}</em></span><button data-pwd>修改密码</button><button data-logout>退出</button></div></header><section id="content"></section></main>`;
  bindShell();
  renderPage();
}

function bindShell() {
  document.querySelectorAll('#sidebar-nav [data-go]').forEach(button => {
    button.onclick = () => go(button.dataset.go);
  });
  document.querySelectorAll('#sidebar-nav [data-group]').forEach(button => {
    button.onclick = () => {
      const item = MENU.filter(x => !x.admin || S().user.role === 'admin')[Number(button.dataset.group)];
      if (!item) return;
      if (expanded.has(item.label)) expanded.delete(item.label);
      else expanded.add(item.label);
      document.getElementById('sidebar-nav').innerHTML = sidebarHTML();
      bindShell();
    };
  });
  document.querySelector('[data-logout]').onclick = () => run(async () => {
    await api('logout', {});
    location.reload();
  });
  document.querySelector('[data-pwd]').onclick = passwordDialog;
}

function renderPage() {
  const host = document.getElementById('content');
  host.innerHTML = '';
  PAGES[current].render(host);
}

export function repaint() {
  paint();
}

export function passwordDialog() {
  modal(`<form id="pwd-form"><label>原密码<input name="old" type="password" required autocomplete="current-password"></label>
    <label>新密码<input name="new" type="password" required minlength="6" autocomplete="new-password"></label>
    <label>确认新密码<input name="confirm" type="password" required minlength="6" autocomplete="new-password"></label>
    <p class="tiny">修改密码后需要使用新密码重新登录。</p>
    <div class="dialog-actions"><button type="button" data-close>取消</button><button class="primary">保存</button></div></form>`, { title: '修改密码' });
  document.getElementById('pwd-form').onsubmit = event => {
    event.preventDefault();
    const form = formObject(event.target);
    run(async () => {
      if (form.new !== form.confirm) throw new Error('两次输入的新密码不一致');
      await api('password', { old: form.old, new: form.new });
      closeModal();
      toast('密码已修改，请重新登录');
      setTimeout(() => location.reload(), 1200);
    });
  };
}

function loginScreen(setup) {
  document.getElementById('app').innerHTML = `<div class="login"><div class="badge">RESEARCH OPERATING SYSTEM</div>
    <h1>研枢 · ${setup ? '初始化管理员' : '欢迎回来'}</h1>
    <p class="muted">期货研究管理平台 · 前后端分离部署版</p>
    <form id="login-form"><label>账号<input name="name" required autocomplete="username"></label>
    <label>密码<input name="password" type="password" required minlength="${setup ? 6 : 1}" autocomplete="${setup ? 'new-password' : 'current-password'}" placeholder="至少6位"></label>
    <label class="person inline"><input type="checkbox" name="remember" checked>保持登录状态（30天内免登录）</label>
    <button class="primary block">${setup ? '创建管理员并进入' : '登录工作空间'}</button></form>
    <p class="muted tiny">${setup ? '初始化后请创建研究复核、合规审核、发布专员账号。' : '账号由管理员分配；未勾选保持登录时，30分钟无操作自动退出。'}</p></div>`;
  document.getElementById('login-form').onsubmit = event => {
    event.preventDefault();
    const form = formObject(event.target);
    run(async () => {
      await api(setup ? 'setup' : 'login', { name: form.name, password: form.password, remember: Boolean(form.remember) });
      await refresh();
      paint();
    });
  };
}

export async function start() {
  window.App = actions;
  actions.go = go;
  actions.page = page;
  actions.repaint = repaint;
  actions.refreshPage = repaint;
  actions.passwordDialog = passwordDialog;
  try {
    const bootstrap = await api('bootstrap');
    if (bootstrap.setup) return loginScreen(true);
    await refresh();
    paint();
  } catch (error) {
    if (String(error.message).includes('请先登录')) return loginScreen(false);
    try {
      const bootstrap = await api('bootstrap');
      loginScreen(Boolean(bootstrap.setup));
    } catch {
      toast(error.message || '服务不可用');
    }
  }
}
