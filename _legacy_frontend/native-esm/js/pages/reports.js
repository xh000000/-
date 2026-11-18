/* 研报中心 / 审核中心：列表、筛选、操作口径与新建向导。 */
import { S, api, refresh, store } from '../core/api.js';
import { esc, run, modal, closeModal, confirmAction, formObject, statusText, localTime, today, empty, toast } from '../core/ui.js';
import { reportTable, bindReportTable, sortReports, isOwner } from './widgets.js';
import { actions } from '../core/actions.js';
import * as editor from './editor.js';

export const filters = { scope: 'mine', search: '', category: '', status: '', dateKind: 'published_at', from: '', to: '', sort: 'status' };
export let selected = null;
let approvalScope = 'pending';

export function open(id) {
  selected = id;
  document.body.classList.add('editing');
  actions.refreshPage?.();
}

export function active() {
  return Boolean(selected);
}

export function back() {
  selected = null;
  document.body.classList.remove('editing');
  actions.refreshPage?.();
}

export function guard() {
  return selected ? editor.unsavedMessage() : '';
}

export function render(c) {
  if (selected) return editor.render(c, selected, back);
  if (actions.page?.() === '审核中心') return renderApproval(c);
  renderList(c);
}

function leafCategories() {
  return S().categories.filter(cat => {
    const node = S().category_tree.find(n => n.id === cat.id);
    return node && !node.folder && node.effective_enabled;
  });
}

function reportDate(report, kind) {
  const meta = report.metadata ? JSON.parse(report.metadata) : null;
  const raw = kind === 'report_date' ? meta?.report_date : report[kind];
  return String(raw || '').slice(0, 10);
}

function currentList() {
  const me = S().user;
  const keyword = filters.search.toLowerCase();
  const list = S().reports.filter(report => {
    const meta = report.metadata ? JSON.parse(report.metadata) : null;
    const scopeOk = actions.page?.() === '审核中心'
      ? true
      : filters.scope === 'public' ? report.status === '已发布'
        : filters.scope === 'mine' ? (me.role === 'admin' || report.author === me.id) && (!meta || meta.collaboration === 'personal')
          : Boolean(meta && meta.collaboration === 'shared' && (me.role === 'admin' || report.author === me.id || meta.collaborators.includes(me.id)));
    const date = reportDate(report, filters.dateKind);
    return scopeOk
      && (!filters.category || report.category_id === Number(filters.category))
      && (!filters.status || statusText(report) === filters.status)
      && (!filters.from || date >= filters.from)
      && (!filters.to || date <= filters.to)
      && `${report.title} ${report.author_name}`.toLowerCase().includes(keyword);
  });
  if (filters.sort === 'title') return list.sort((a, b) => a.title.localeCompare(b.title, 'zh'));
  if (filters.sort === 'updated') return list.sort((a, b) => String(b.updated).localeCompare(String(a.updated)));
  return sortReports(list);
}

function renderList(c) {
  const canCreate = ['admin', 'researcher'].includes(S().user.role);
  c.innerHTML = `<div class="page-body">
    <div class="row spread page-head"><div><h2>研报中心</h2>
      <p class="caption">按「我的 / 共享 / 公共」查看研报；状态口径为待提交 → 待审批 → 已通过 → 已发布，驳回后回到可编辑状态。</p></div>
      <button class="primary" data-new ${canCreate ? '' : 'disabled'}>＋ 添加研报</button></div>
    <div class="report-module">
    <div class="report-filters">
      <input id="rp-search" placeholder="搜索标题 / 创建人" aria-label="标题或创建人" value="${esc(filters.search)}">
      <select id="rp-category" aria-label="类型筛选"><option value="">类型筛选</option>${leafCategories().map(x => `<option value="${x.id}" ${String(x.id) === filters.category ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}</select>
      <select id="rp-status" aria-label="状态筛选"><option value="">状态筛选</option>${['待提交', '待审批', '已驳回', '已通过', '已发布'].map(x => `<option ${x === filters.status ? 'selected' : ''}>${x}</option>`).join('')}</select>
      <select id="rp-datekind" aria-label="时间类型"><option value="published_at">发布时间</option><option value="updated">更新时间</option><option value="report_date">创建时间</option></select>
      <input type="date" id="rp-from" aria-label="开始日期" value="${esc(filters.from)}"><span>至</span><input type="date" id="rp-to" aria-label="结束日期" value="${esc(filters.to)}">
      <select id="rp-sort" aria-label="排序"><option value="status">状态优先</option><option value="updated">更新时间降序</option><option value="title">标题排序</option></select>
    </div>
    <div class="report-tabs">${[['mine', '我的研报'], ['shared', '共享研报'], ['public', '公共研报']].map(([id, label]) => `<button data-scope="${id}" class="${filters.scope === id ? 'active' : ''}">${label}</button>`).join('')}</div>
    <div id="rp-list"></div></div></div>`;
  const listHost = c.querySelector('#rp-list');
  const paint = () => {
    listHost.innerHTML = reportTable(currentList());
    bindReportTable(listHost, id => open(id), id => more(id));
  };
  c.querySelector('[data-new]').onclick = () => newReport();
  c.querySelectorAll('[data-scope]').forEach(button => button.onclick = () => {
    filters.scope = button.dataset.scope;
    c.querySelectorAll('[data-scope]').forEach(x => x.classList.toggle('active', x.dataset.scope === filters.scope));
    paint();
  });
  const bind = (id, key, parse = String) => {
    const el = c.querySelector(id);
    el.value = filters[key];
    el.oninput = el.onchange = () => { filters[key] = parse(el.value); paint(); };
  };
  bind('#rp-search', 'search');
  bind('#rp-category', 'category');
  bind('#rp-status', 'status');
  bind('#rp-datekind', 'dateKind');
  bind('#rp-from', 'from');
  bind('#rp-to', 'to');
  bind('#rp-sort', 'sort');
  paint();
}

function renderApproval(c) {
  const list = S().reports.filter(report => approvalScope === 'initiated' ? report.author === S().user.id
    : approvalScope === 'handled' ? report.handled_by_me
      : (report.allowed_actions || []).some(x => ['通过', '退回', '发布'].includes(x)));
  c.innerHTML = `<div class="page-body">
    <div class="row spread page-head"><div><h2>审核中心</h2>
      <p class="caption">按当前账号的节点资格显示待处理事项；已处理记录可在报告的版本留痕中查看。</p></div></div>
    <div class="report-module">
    <div class="report-tabs">${[['pending', '待处理'], ['handled', '已处理'], ['initiated', '我发起的']].map(([id, label]) => `<button data-scope="${id}" class="${approvalScope === id ? 'active' : ''}">${label}</button>`).join('')}</div>
    <div id="ap-list">${reportTable(sortReports(list))}</div></div></div>`;
  const host = c.querySelector('#ap-list');
  bindReportTable(host, id => open(id), id => more(id));
  c.querySelectorAll('[data-scope]').forEach(button => button.onclick = () => {
    approvalScope = button.dataset.scope;
    renderApproval(c);
  });
}

export function newReport() {
  if (!['admin', 'researcher'].includes(S().user.role)) return toast('当前角色没有创建研报权限');
  const cats = leafCategories();
  if (!cats.length) return toast('请管理员先创建并启用末级分类');
  modal(`<form id="new-report" class="basic-form">
    <div class="basic-row"><span>新增方式</span><div class="radio-line"><label><input type="radio" name="mode" value="new" checked>新增报告</label><label><input type="radio" name="mode" value="inherit">继承报告</label></div></div>
    <div class="basic-row required"><span>报告分类</span><select name="category_id" id="nr-category" required>${cats.map(x => `<option value="${x.id}">${esc(x.name)}</option>`).join('')}</select></div>
    <div class="basic-row" id="nr-inherit-row" hidden><span>继承报告</span><select name="inherit_id" id="nr-inherit"></select></div>
    <div class="basic-row required"><span>报告标题</span><input name="title" id="nr-title" required maxlength="200"></div>
    <div class="basic-row"><span>报告摘要</span><textarea name="summary" maxlength="2000" placeholder="选填，用于列表摘要列"></textarea></div>
    <div class="basic-row"><span>署名作者</span><select name="byline_id" id="nr-byline" required></select></div>
    <div class="basic-row"><span>研究品种</span><select name="commodity" id="nr-commodity" required></select></div>
    <div class="basic-row"><span>创建日期</span><input type="date" name="report_date" id="nr-date" value="${today()}" required></div>
    <div class="basic-row"><span>协作方式</span><div class="radio-line"><label><input type="radio" name="collaboration" value="personal" checked>个人</label><label><input type="radio" name="collaboration" value="shared">多人协作</label></div></div>
    <div class="basic-row" id="nr-people-row" hidden><span>协作人</span><div>${S().members.filter(x => x.id !== S().user.id && ['researcher', 'admin'].includes(x.role)).map(x => `<label class="person block"><input type="checkbox" name="people" value="${x.id}">${esc(x.name)}</label>`).join('') || '<small class="muted">请先创建研究员账号</small>'}</div></div>
    <div class="basic-row"><span>报告布局</span><div class="radio-line"><label><input type="radio" name="layout" value="flow" checked>常规布局</label><label><input type="radio" name="layout" value="grid">智能布局</label><label><input type="radio" name="layout" value="free">自由布局</label></div></div>
    <div class="basic-row"><span>公开发布</span><div class="radio-line"><label><input type="radio" name="public" value="true" checked>是 · 发布后所有人可见</label><label><input type="radio" name="public" value="false">否 · 仅参与者与审批人可见</label></div></div>
    <div class="caption" id="nr-help"></div>
    <div class="dialog-actions"><button type="button" data-close>取消</button><button class="primary">确定并进入编辑器</button></div></form>`, { title: '添加研报', wide: true });

  const q = id => document.getElementById(id);
  let commodity = '';
  const syncTitle = () => {
    const cat = S().categories.find(x => x.id === Number(q('nr-category').value));
    if (!cat) return;
    q('nr-title').value = String(cat.config.title_pattern || '{品种}{类型}｜{日期}')
      .replaceAll('{品种}', commodity).replaceAll('{类型}', cat.config.kind).replaceAll('{日期}', q('nr-date').value);
  };
  const syncCategory = () => {
    const cat = S().categories.find(x => x.id === Number(q('nr-category').value));
    if (!cat) return;
    const cfg = cat.config;
    q('nr-byline').innerHTML = S().authors.filter(a => a.enabled && JSON.parse(a.types).includes(cfg.kind)).map(a => `<option value="${a.id}">${esc(a.name)}</option>`).join('');
    const usable = cfg.commodities.filter(name => S().commodities.some(x => x.name === name && x.enabled));
    q('nr-commodity').innerHTML = usable.map(x => `<option>${esc(x)}</option>`).join('');
    commodity = usable[0] || '';
    q('nr-inherit').innerHTML = S().reports.filter(r => r.document && r.category_id === cat.id && r.status === '已发布')
      .sort((a, b) => String(b.updated).localeCompare(String(a.updated))).map(r => `<option value="${r.id}">${esc(r.title)} · v${r.version}</option>`).join('');
    q('nr-help').textContent = '分类关联品种：' + cfg.commodities.join('、') + '；分类、新增方式、协作方式与布局创建后不可修改。';
    if (!q('nr-byline').options.length) q('nr-help').textContent += ' 当前分类没有可用署名作者，请先在作者管理中维护。';
    syncTitle();
  };
  q('nr-category').onchange = syncCategory;
  q('nr-commodity').onchange = () => { commodity = q('nr-commodity').value; syncTitle(); };
  q('nr-date').onchange = syncTitle;
  document.getElementById('new-report').onchange = event => {
    const form = new FormData(document.getElementById('new-report'));
    q('nr-inherit-row').hidden = form.get('mode') !== 'inherit';
    q('nr-people-row').hidden = form.get('collaboration') !== 'shared';
  };
  syncCategory();
  document.getElementById('new-report').onsubmit = event => {
    event.preventDefault();
    const form = new FormData(event.target);
    run(async () => {
      const inherit = form.get('mode') === 'inherit';
      if (inherit && !q('nr-inherit').value) throw new Error('该分类暂无可继承的已发布报告');
      if (!q('nr-byline').value) throw new Error('请先在作者管理中添加可用署名作者');
      const result = await api('reports', {
        manual: true, category_id: Number(q('nr-category').value), title: q('nr-title').value,
        summary: form.get('summary') || '', byline_id: Number(q('nr-byline').value), report_date: q('nr-date').value,
        commodity, collaboration: form.get('collaboration'), collaborators: form.getAll('people').map(Number),
        layout: form.get('layout'), public: form.get('public') === 'true', inherit_id: inherit ? Number(q('nr-inherit').value) : null,
      });
      closeModal();
      await refresh();
      open(result.id);
      toast('报告已创建');
    });
  };
}

export function more(id) {
  const report = S().reports.find(r => r.id === id);
  if (!report) return;
  const owner = isOwner(report);
  const editable = report.author === S().user.id && ['草稿', '已退回'].includes(report.status);
  const actionsList = (report.allowed_actions || []);
  const buttons = [];
  buttons.push(`<button data-act="open">${editable ? '编辑' : '查看'}</button>`);
  if (report.allowed_actions && report.allowed_actions.includes('提交')) buttons.push('<button data-act="submit">提交审批</button>');
  if (actionsList.includes('通过')) buttons.push('<button class="primary" data-act="approve">审核通过</button>');
  if (actionsList.includes('退回')) buttons.push('<button data-act="reject">驳回</button>');
  if (actionsList.includes('发布')) buttons.push('<button class="primary" data-act="publish">发布</button>');
  if (report.can_schedule) buttons.push('<button data-act="schedule">定时发布</button>');
  if (owner && ['草稿', '已退回'].includes(report.status)) buttons.push('<button class="danger" data-act="delete">删除</button>');
  if (owner && !['草稿', '已退回'].includes(report.status)) buttons.push('<button data-act="withdraw">撤销</button>');
  if (report.status === '已发布' || report.status === '待发布') buttons.push('<button data-act="print">下载 PDF</button>');
  modal(`<div class="dialog-body"><h3>${esc(report.title)}</h3><p class="muted">${esc(statusText(report))} · v${report.version} · 第${report.issue || 1}期</p>
    <div class="row">${buttons.join('')}</div>
    <p class="caption">PDF 通过服务端打印页生成（浏览器「打印 → 另存为 PDF」）；长图导出需引入前端截图库，暂未实现。</p></div>`, { title: '研报操作' });
  document.getElementById('modal').querySelectorAll('[data-act]').forEach(button => {
    button.onclick = () => {
      const act = button.dataset.act;
      closeModal();
      if (act === 'open') open(id);
      if (act === 'print') window.open('/api/report-print/' + id, '_blank');
      if (act === 'delete') confirmAction('删除研报', '从业务列表移除该草稿，数据库记录保留。', () => run(async () => {
        await api('report-delete', { id });
        await refresh();
        actions.refreshPage?.();
        toast('已删除');
      }), '删除');
      if (act === 'schedule') scheduleDialog(id);
      if (act === 'withdraw') withdrawDialog(id);
      if (act === 'submit' || act === 'approve' || act === 'reject' || act === 'publish') transitionDialog(id, act);
    };
  });
}

function transitionDialog(id, act) {
  const map = { submit: ['提交', ['草稿', '已退回']], approve: ['通过', ['研究复核', '合规审核']], reject: ['退回', ['研究复核', '合规审核']], publish: ['发布', ['待发布']] };
  const [name, states] = map[act];
  const needNote = name === '退回';
  modal(`<form id="trans-form"><p class="muted">当前状态：${esc(states.map(s => statusText({ status: s })).join(' / '))}</p>
    ${needNote ? '<label>驳回理由<textarea name="note" required style="min-height:90px"></textarea></label>' : ''}
    <div class="dialog-actions"><button type="button" data-close>取消</button><button class="primary">确认${name}</button></div></form>`, { title: '流程操作' });
  document.getElementById('trans-form').onsubmit = event => {
    event.preventDefault();
    run(async () => {
      const report = S().reports.find(r => r.id === id);
      await api('transition', { id, action: name, note: formObject(event.target).note || '', expected_status: report.status, expected_workflow: report.workflow_state });
      closeModal();
      await refresh();
      actions.refreshPage?.();
      toast('流程已更新');
    });
  };
}

function withdrawDialog(id) {
  modal(`<form id="wd-form"><p>撤销后退出当前发布 / 审批状态，历史定稿与审批记录保留。</p><label>撤销原因<textarea name="note" required style="min-height:90px"></textarea></label>
    <div class="dialog-actions"><button type="button" data-close>取消</button><button class="primary">确认撤销</button></div></form>`, { title: '撤销发布或审批' });
  document.getElementById('wd-form').onsubmit = event => {
    event.preventDefault();
    run(async () => {
      await api('report-withdraw', { id, note: formObject(event.target).note });
      closeModal();
      await refresh();
      actions.refreshPage?.();
      toast('已撤销');
    });
  };
}

function scheduleDialog(id) {
  modal(`<form id="sc-form"><label>定时发布时间<input type="datetime-local" name="at" required></label>
    <p class="caption">到达预约时间后由服务端自动发布，发布记录写入操作留痕。留空提交则取消定时。</p>
    <div class="dialog-actions"><button type="button" data-close>取消</button><button class="primary">保存定时</button></div></form>`, { title: '定时发布' });
  document.getElementById('sc-form').onsubmit = event => {
    event.preventDefault();
    run(async () => {
      await api('report-schedule', { id, at: formObject(event.target).at });
      closeModal();
      await refresh();
      actions.refreshPage?.();
      toast('已设置定时发布');
    });
  };
}
