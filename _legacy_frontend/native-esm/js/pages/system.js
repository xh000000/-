/* 系统设置：部门/分组与账号、角色与菜单权限、基本配置。 */
import { S, api, refresh } from '../core/api.js';
import { esc, run, toast, modal, closeModal, formObject, ROLE_NAMES, localTime, empty } from '../core/ui.js';
import { actions } from '../core/actions.js';

const MENU_KEYS = ['工作台', '数据中心', '研报中心', '审核中心', '云盘', '文档管理库', '素材库', '分类配置', '作者管理', '品种管理', '审批流配置', '角色管理', '部门管理', '系统管理'];

export function renderDepartments(c) {
  const depts = S().departments || [];
  const users = S().users || [];
  const tops = depts.filter(d => !d.parent_id).sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
  const rows = [];
  tops.forEach(top => {
    rows.push(deptRow(top, 0));
    depts.filter(d => d.parent_id === top.id).sort((a, b) => a.sort_order - b.sort_order || a.id - b.id).forEach(child => rows.push(deptRow(child, 1)));
  });
  c.innerHTML = `<div class="page-body">
    <div class="row spread page-head"><div><h2>部门管理</h2><p class="caption">部门最多两级（部门 → 分组）；账号归属到部门或分组，禁用后不可登录。</p></div>
      <div class="row"><button data-dept>＋ 新建部门</button><button class="primary" data-user>＋ 添加用户</button></div></div>
    <div class="panel"><div class="tablewrap"><table><thead><tr><th>部门 / 分组</th><th>层级</th><th>账号数</th><th>状态</th><th>操作</th></tr></thead>
      <tbody>${rows.join('') || '<tr><td colspan="5" class="empty">暂无部门</td></tr>'}</tbody></table></div></div>
    <div class="panel"><h3>账号列表</h3><div class="tablewrap"><table><thead><tr><th>姓名</th><th>角色</th><th>部门</th><th>手机</th><th>职务</th><th>状态</th><th>最近登录</th><th>操作</th></tr></thead>
      <tbody>${users.map(u => `<tr><td>${esc(u.name)}</td><td>${esc(u.role_name || ROLE_NAMES[u.role])}</td><td>${esc(u.dept_name || '—')}</td>
        <td>${esc(u.phone || '—')}</td><td>${esc(u.title || '—')}</td>
        <td><span class="badge ${u.enabled ? 'green' : 'gray'}">${u.enabled ? '启用' : '停用'}</span></td>
        <td>${esc(localTime(u.last_login_at))}</td>
        <td class="row"><button class="text-action" data-uedit="${u.id}">编辑</button><button class="text-action" data-ureset="${u.id}">重置密码</button>
        <button class="text-action" data-utoggle="${u.id}">${u.enabled ? '禁用' : '启用'}</button></td></tr>`).join('') || '<tr><td colspan="8" class="empty">暂无账号</td></tr>'}</tbody></table></div></div></div>`;
  c.querySelector('[data-dept]').onclick = () => deptDialog(null, c);
  c.querySelector('[data-user]').onclick = () => userDialog(null, c);
  c.querySelectorAll('[data-dedit]').forEach(b => b.onclick = () => deptDialog(depts.find(d => d.id === Number(b.dataset.dedit)), c));
  c.querySelectorAll('[data-ddel]').forEach(b => b.onclick = () => run(async () => {
    await api('departments', { action: 'delete', id: Number(b.dataset.ddel) });
    await refresh(); renderDepartments(c); toast('已删除');
  }));
  c.querySelectorAll('[data-uedit]').forEach(b => b.onclick = () => userDialog(S().users.find(u => u.id === Number(b.dataset.uedit)), c));
  c.querySelectorAll('[data-utoggle]').forEach(b => b.onclick = () => run(async () => {
    await api('users', { action: 'toggle', id: Number(b.dataset.utoggle) });
    await refresh(); renderDepartments(c); toast('状态已更新');
  }));
  c.querySelectorAll('[data-ureset]').forEach(b => b.onclick = () => resetPassword(Number(b.dataset.ureset), c));
}

function deptRow(dept, level) {
  return `<tr><td style="padding-left:${12 + level * 26}px">${dept.parent_id ? '－' : '▸'} ${esc(dept.name)}</td>
    <td>${level + 1}级</td><td>${dept.users}</td>
    <td><span class="badge ${dept.effective_enabled ? 'green' : 'gray'}">${dept.effective_enabled ? '启用' : '停用'}</span></td>
    <td class="row"><button class="text-action" data-dedit="${dept.id}">编辑</button><button class="text-action" data-ddel="${dept.id}">删除</button></td></tr>`;
}

function deptDialog(dept, host) {
  modal(`<form id="dept-form"><label>名称<input name="name" required maxlength="40" value="${esc(dept?.name || '')}"></label>
    <label>上级部门<select name="parent_id"><option value="">无 · 一级部门</option>${(S().departments || []).filter(d => !d.parent_id && d.id !== dept?.id).map(d => `<option value="${d.id}" ${dept?.parent_id === d.id ? 'selected' : ''}>${esc(d.name)}</option>`).join('')}</select></label>
    <label>排序<input type="number" name="sort_order" value="${dept?.sort_order ?? 0}"></label>
    <label class="person inline"><input type="checkbox" name="enabled" ${!dept || dept.enabled ? 'checked' : ''}>启用</label>
    <div class="dialog-actions"><button type="button" data-close>取消</button><button class="primary">保存</button></div></form>`, { title: dept ? '编辑部门' : '新建部门' });
  document.getElementById('dept-form').onsubmit = event => {
    event.preventDefault();
    const values = formObject(event.target);
    run(async () => {
      await api('departments', { action: dept ? 'update' : 'create', id: dept?.id, name: values.name, parent_id: values.parent_id ? Number(values.parent_id) : null, sort_order: Number(values.sort_order || 0), enabled: Boolean(values.enabled) });
      closeModal(); await refresh(); renderDepartments(host); toast('已保存');
    });
  };
}

function userDialog(user, host) {
  const roles = S().roles || [];
  const depts = S().departments || [];
  modal(`<form id="user-form"><label>姓名<input name="name" required maxlength="40" value="${esc(user?.name || '')}"></label>
    ${user ? '' : '<label>初始密码<input name="password" type="password" required minlength="6" placeholder="至少6位"></label>'}
    <label>角色<select name="role_id">${roles.map(r => `<option value="${r.id}" ${user?.role_id === r.id ? 'selected' : ''}>${esc(r.name)}（${esc(ROLE_NAMES[r.base_role] || r.base_role)}）</option>`).join('')}</select></label>
    <label>部门<select name="dept_id"><option value="">未分配</option>${depts.map(d => `<option value="${d.id}" ${user?.dept_id === d.id ? 'selected' : ''}>${esc(d.parent_name ? d.parent_name + ' / ' : '')}${esc(d.name)}</option>`).join('')}</select></label>
    <label>手机号<input name="phone" maxlength="20" value="${esc(user?.phone || '')}"></label>
    <label>职务<input name="title" maxlength="40" value="${esc(user?.title || '')}"></label>
    <label class="person inline"><input type="checkbox" name="enabled" ${!user || user.enabled ? 'checked' : ''}>启用账号</label>
    <p class="caption">角色决定可访问菜单；审批资格由角色类型（研究员/复核/合规/发布）决定。</p>
    <div class="dialog-actions"><button type="button" data-close>取消</button><button class="primary">保存</button></div></form>`, { title: user ? '编辑账号' : '添加用户' });
  document.getElementById('user-form').onsubmit = event => {
    event.preventDefault();
    const values = formObject(event.target);
    run(async () => {
      await api('users', { action: user ? 'update' : 'create', id: user?.id, name: values.name, password: values.password, role_id: Number(values.role_id), dept_id: values.dept_id ? Number(values.dept_id) : null, phone: values.phone, title: values.title, enabled: Boolean(values.enabled) });
      closeModal(); await refresh(); renderDepartments(host); toast('已保存');
    });
  };
}

function resetPassword(id, host) {
  modal(`<form id="reset-form"><label>新密码<input name="password" type="password" required minlength="6"></label>
    <p class="caption">重置后该账号所有登录会话立即失效。</p>
    <div class="dialog-actions"><button type="button" data-close>取消</button><button class="primary">重置</button></div></form>`, { title: '重置密码' });
  document.getElementById('reset-form').onsubmit = event => {
    event.preventDefault();
    run(async () => {
      await api('users', { action: 'reset', id, password: formObject(event.target).password });
      closeModal(); toast('密码已重置');
    });
  };
}

export function renderRoles(c) {
  const roles = S().roles || [];
  c.innerHTML = `<div class="page-body"><div class="row spread page-head"><div><h2>角色管理</h2>
      <p class="caption">角色 = 一种审批身份 + 一组可见菜单；内置角色不可删除，可调整菜单权限。</p></div>
      <button class="primary" data-add>＋ 添加角色</button></div>
    <div class="panel"><div class="tablewrap"><table><thead><tr><th>角色名称</th><th>角色类型</th><th>菜单权限</th><th>账号数</th><th>操作</th></tr></thead><tbody>
    ${roles.map(r => `<tr><td>${esc(r.name)} ${r.builtin ? '<span class="badge gray">内置</span>' : ''}</td><td>${esc(ROLE_NAMES[r.base_role] || r.base_role)}</td>
      <td>${r.menus.includes('*') ? '全部菜单' : r.menus.length + ' 项'}</td><td>${r.users}</td>
      <td class="row"><button class="text-action" data-edit="${r.id}">编辑</button>${r.builtin ? '' : `<button class="text-action" data-del="${r.id}">删除</button>`}</td></tr>`).join('')}
    </tbody></table></div></div></div>`;
  c.querySelector('[data-add]').onclick = () => roleDialog(null, c);
  c.querySelectorAll('[data-edit]').forEach(b => b.onclick = () => roleDialog(roles.find(r => r.id === Number(b.dataset.edit)), c));
  c.querySelectorAll('[data-del]').forEach(b => b.onclick = () => run(async () => {
    await api('roles', { action: 'delete', id: Number(b.dataset.del) });
    await refresh(); renderRoles(c); toast('已删除');
  }));
}

function roleDialog(role, host) {
  const isAdminRole = role?.base_role === 'admin';
  modal(`<form id="role-form"><label>角色名称<input name="name" required maxlength="30" value="${esc(role?.name || '')}" ${role?.builtin && isAdminRole ? 'readonly' : ''}></label>
    <label>角色类型<select name="base_role" ${role?.builtin ? 'disabled' : ''}>${Object.entries(ROLE_NAMES).map(([k, v]) => `<option value="${k}" ${role?.base_role === k ? 'selected' : ''}>${v}</option>`).join('')}</select></label>
    <p class="caption">菜单权限${isAdminRole ? '（管理员固定拥有全部菜单）' : ''}</p>
    <div class="row">${MENU_KEYS.map(k => `<label class="person inline"><input type="checkbox" name="menu" value="${k}" ${isAdminRole || role?.menus?.includes(k) ? 'checked' : ''} ${isAdminRole ? 'disabled' : ''}>${esc(k)}</label>`).join('')}</div>
    <div class="dialog-actions"><button type="button" data-close>取消</button><button class="primary">保存</button></div></form>`, { title: role ? '编辑角色' : '添加角色', wide: true });
  document.getElementById('role-form').onsubmit = event => {
    event.preventDefault();
    const form = event.target;
    const values = formObject(form);
    run(async () => {
      await api('roles', { action: role ? 'update' : 'create', id: role?.id, name: values.name, base_role: values.base_role || role.base_role, menus: new FormData(form).getAll('menu') });
      closeModal(); await refresh(); renderRoles(host); toast('已保存');
    });
  };
}

export function renderSettings(c) {
  const user = S().user;
  c.innerHTML = `<div class="page-body">
    <div class="row spread page-head"><div><h2>基本配置</h2>
      <p class="caption">外部模型与账号信息；研报审批规则在「审批流配置」与「角色管理」中维护。</p></div></div>
    <div class="panel"><h3>基本配置</h3>
      <p>外部模型：<span class="badge ${S().ai ? 'green' : 'gray'}">${S().ai ? '已配置' : '未配置'}</span>　模型：${esc(S().model || '未配置')}</p>
      <p class="caption">通过服务端环境变量 AI_BASE_URL / AI_API_KEY / AI_MODEL 配置 OpenAI 兼容接口；凭证不返回浏览器、不写入研报，修改后需重启服务。</p></div>
    <div class="panel"><h3>我的账号</h3>
      <p>姓名：${esc(user.name)}　角色：${esc(ROLE_NAMES[user.role] || user.role)}　部门：${esc((S().users.find(u => u.id === user.id) || {}).dept_name || '—')}</p>
      <div class="row"><button class="primary" data-pwd>修改密码</button></div>
      <p class="caption">修改密码后需要重新登录；未勾选「保持登录」的会话 30 分钟无操作自动失效。</p></div>
    <div class="panel"><h3>研报审批</h3>
      <p class="caption">审批流可在「审批流配置」按分类设置多节点；未配置审批流的分类使用分类自带的审批节点。作者不能审核或发布自己的报告。</p>
      <div class="row"><button data-go-flows>前往审批流配置</button><button data-go-roles>前往角色管理</button></div></div></div>`;
  c.querySelector('[data-pwd]').onclick = () => actions.passwordDialog();
  c.querySelector('[data-go-flows]').onclick = () => actions.go('审批流配置');
  c.querySelector('[data-go-roles]').onclick = () => actions.go('角色管理');
}
