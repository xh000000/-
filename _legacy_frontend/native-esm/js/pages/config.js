/* 研报配置：分类树、分类的章节与审批配置、署名作者、研究品种、独立审批流。 */
import { S, api, refresh } from '../core/api.js';
import { esc, run, toast, modal, closeModal, formObject, ROLE_NAMES, empty } from '../core/ui.js';
import { actions } from '../core/actions.js';

let cfgDraft = null;
const MODE_NAMES = { any: '或签', all: '会签', sequential: '依次审批' };
const uid = () => (crypto.randomUUID ? crypto.randomUUID() : 'x' + Date.now() + Math.random().toString(16).slice(2));

function orderedTree(parent = null) {
  return S().category_tree.filter(n => n.parent_id === parent)
    .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id)
    .flatMap(n => [n, ...orderedTree(n.id)]);
}

export function renderCategories(c) {
  if (cfgDraft) return renderConfigForm(c);
  const nodes = orderedTree();
  c.innerHTML = `<div class="page-body"><div class="row spread page-head"><div><h2>研报分类树</h2>
      <p class="caption">最多三级。末级分类配置报告章节结构与审批；上级分类用于组织目录。</p></div>
      <button class="primary" data-add>＋ 添加分类</button></div>
    <div class="panel"><div class="tablewrap"><table><thead><tr><th>分类</th><th>层级</th><th>状态</th><th>排序</th><th>操作</th></tr></thead><tbody>
    ${nodes.map(n => `<tr><td style="padding-left:${12 + (n.depth - 1) * 26}px">${n.folder ? '▸' : '▤'} ${esc(n.label)}</td>
      <td>${n.depth}级</td><td><span class="badge ${n.effective_enabled ? 'green' : 'gray'}">${n.effective_enabled ? '启用' : '停用'}</span></td>
      <td>${n.sort_order}</td><td class="row"><button class="text-action" data-edit="${n.id}">编辑分类</button>${n.folder ? '' : `<button class="text-action" data-config="${n.id}">章节与审批配置</button>`}</td></tr>`).join('') || '<tr><td colspan="5" class="empty">暂无分类</td></tr>'}
    </tbody></table></div></div></div>`;
  c.querySelector('[data-add]').onclick = () => treeDialog(null);
  c.querySelectorAll('[data-edit]').forEach(b => b.onclick = () => treeDialog(Number(b.dataset.edit)));
  c.querySelectorAll('[data-config]').forEach(b => b.onclick = () => {
    const cat = S().categories.find(x => x.id === Number(b.dataset.config));
    if (!cat) return;
    cfgDraft = { id: cat.id, name: cat.name, revision: cat.revision, enabled: cat.enabled, config: JSON.parse(JSON.stringify(cat.config)) };
    renderCategories(c);
  });
}

function treeDialog(id) {
  const node = S().category_tree.find(n => n.id === id);
  modal(`<form id="tree-form"><label>分类名称<input name="label" required maxlength="40" value="${esc(node?.label || '')}"></label>
    <label>上级分类<select name="parent_id"><option value="">无 · 一级分类</option>${orderedTree().filter(n => n.id !== id && n.depth < 3).map(n => `<option value="${n.id}" ${node?.parent_id === n.id ? 'selected' : ''}>${esc(n.name)}</option>`).join('')}</select></label>
    ${id ? '' : `<label>用途<select name="folder"><option value="false">末级分类 · 用于创建报告</option><option value="true">目录 · 用于组织子分类</option></select></label>`}
    <label>后台排序<input type="number" name="sort_order" value="${node?.sort_order ?? 0}"></label>
    <label class="person inline"><input type="checkbox" name="enabled" ${!node || node.enabled ? 'checked' : ''}>启用</label>
    <p class="caption">系统会校验循环引用、三级深度与同级重名；父级停用时子级不可用于创建报告。</p>
    <div class="dialog-actions"><button type="button" data-close>取消</button><button class="primary">保存</button></div></form>`, { title: id ? '编辑分类' : '新增分类' });
  document.getElementById('tree-form').onsubmit = event => {
    event.preventDefault();
    const values = formObject(event.target);
    run(async () => {
      await api('category-tree', { id, label: values.label, parent_id: values.parent_id ? Number(values.parent_id) : null, folder: values.folder === 'true', sort_order: Number(values.sort_order || 0), enabled: Boolean(values.enabled) });
      closeModal();
      await refresh();
      renderCategories(document.getElementById('content'));
      toast('分类已保存');
    });
  };
}

function peopleOptions(role, selected) {
  return S().users.filter(u => u.role === role).map(u => `<option value="${u.id}" ${selected.includes(u.id) ? 'selected' : ''}>${esc(u.name)}</option>`).join('');
}

function renderConfigForm(c) {
  const cfg = cfgDraft.config;
  c.innerHTML = `<div class="page-body"><div class="row spread page-head"><div><h2>${esc(cfgDraft.name)}</h2>
      <p class="caption">配置章节结构、版式与审批节点；保存后只影响后续新建报告，历史报告沿用创建时的配置副本。</p></div>
      <button data-back>返回分类列表</button></div>
    <form id="category-form"><div class="config-grid">
      <div class="panel"><h3>① 基础信息</h3>
        <label>分类名称<input name="name" value="${esc(cfgDraft.name)}" readonly title="名称与层级请在分类树中调整"></label>
        <label>用途说明<input name="description" value="${esc(cfg.description || '')}"></label>
        <div class="row"><label>报告类型<input name="kind" required value="${esc(cfg.kind)}"></label>
        <label class="person inline"><input type="checkbox" name="enabled" ${cfgDraft.enabled ? 'checked' : ''}>启用该分类</label></div>
        <label>可选品种（逗号分隔）<input name="commodities" required value="${esc((cfg.commodities || []).join('，'))}"></label>
        <label>标题规则<input name="title_pattern" required value="${esc(cfg.title_pattern)}"></label>
        <p class="caption">支持 {品种}、{类型}、{日期}，研究员创建时可修改标题。</p></div>
      <div class="panel"><h3>② 版式与品牌</h3>
        <div class="row"><label>默认布局<select name="layout"><option value="flow" ${cfg.layout === 'flow' ? 'selected' : ''}>常规单栏</option><option value="grid" ${cfg.layout === 'grid' ? 'selected' : ''}>智能分栏</option></select></label>
        <label>主题色<input type="color" name="color" value="${esc(cfg.color || '#0758d8')}"></label>
        <label>正文字号<input type="number" name="font_size" min="12" max="24" value="${cfg.font_size || 15}" style="width:90px"></label></div>
        <label>版头文字<input name="header" value="${esc(cfg.header || '')}"></label>
        <label>版尾 / 免责声明<textarea name="footer" style="min-height:80px">${esc(cfg.footer || '')}</textarea></label></div>
      <div class="panel"><div class="row spread"><h3>③ 章节结构</h3><button type="button" data-sec="add">＋ 添加章节</button></div>
        ${(cfg.sections || []).map((s, i) => `<div class="config-section"><div class="row spread"><b>章节 ${i + 1}</b>
          <span><button type="button" data-sec="up" data-i="${i}">↑</button><button type="button" data-sec="down" data-i="${i}">↓</button><button type="button" data-sec="remove" data-i="${i}">删除</button></span></div>
          <input name="sec-title-${i}" value="${esc(s.title)}" placeholder="章节名称" required>
          <div class="row"><label class="person inline"><input type="checkbox" name="sec-required-${i}" ${s.required ? 'checked' : ''}>必填</label>
          <label>章节类型<input name="sec-type-${i}" value="${esc(s.type || '')}" placeholder="如：宏观、供需" style="width:120px"></label></div>
          <textarea name="sec-default-${i}" style="min-height:60px" placeholder="章节默认文字（可选）">${esc(s.default || '')}</textarea>
          <p class="caption">默认关联品种</p><div class="row">${S().commodities.filter(x => x.enabled).map(x => `<label class="person inline"><input type="checkbox" name="sec-commodity-${i}" value="${x.id}" ${(s.commodity_ids || []).includes(x.id) ? 'checked' : ''}>${esc(x.name)}</label>`).join('') || '<span class="caption">暂无品种</span>'}</div></div>`).join('') || '<p class="caption">至少配置一个章节</p>'}</div>
      <div class="panel"><div class="row spread"><h3>④ 审批节点</h3><button type="button" data-node="add">＋ 添加节点</button></div>
        ${(cfg.workflow || []).map((n, i) => `<div class="config-section"><div class="row spread"><b>节点 ${i + 1}</b>
          <span><button type="button" data-node="up" data-i="${i}">↑</button><button type="button" data-node="down" data-i="${i}">↓</button><button type="button" data-node="remove" data-i="${i}">删除</button></span></div>
          <div class="row"><label>节点名称<input name="node-label-${i}" value="${esc(n.label)}" style="width:130px"></label>
          <label>角色<select name="node-role-${i}"><option value="reviewer" ${n.role === 'reviewer' ? 'selected' : ''}>研究复核</option><option value="compliance" ${n.role === 'compliance' ? 'selected' : ''}>合规审核</option></select></label>
          <label>方式<select name="node-mode-${i}">${Object.entries(MODE_NAMES).map(([k, v]) => `<option value="${k}" ${n.mode === k ? 'selected' : ''}>${v}</option>`).join('')}</select></label></div>
          <label>指定审批人（留空表示该角色任一账号可签）<select name="node-users-${i}" multiple size="3">${peopleOptions(n.role, n.users || [])}</select></label></div>`).join('')}
        <p class="caption">流程必须包含一个合规审核节点；会签与依次审批必须指定审批人。</p>
        <div class="row"><button class="primary">保存配置</button><button type="button" data-back>取消</button></div></div>
    </div></form></div>`;
  c.querySelectorAll('[data-back]').forEach(b => b.onclick = () => { cfgDraft = null; renderCategories(c); });
  c.querySelectorAll('[data-sec]').forEach(b => b.onclick = () => {
    capture();
    const list = cfgDraft.config.sections;
    const i = Number(b.dataset.i);
    if (b.dataset.sec === 'add') list.push({ id: uid(), title: '新章节', required: false, default: '', type: '', commodity_ids: [] });
    if (b.dataset.sec === 'remove' && list.length > 1) list.splice(i, 1);
    if (b.dataset.sec === 'up' && i > 0) [list[i - 1], list[i]] = [list[i], list[i - 1]];
    if (b.dataset.sec === 'down' && i < list.length - 1) [list[i + 1], list[i]] = [list[i], list[i + 1]];
    renderConfigForm(c);
  });
  c.querySelectorAll('[data-node]').forEach(b => b.onclick = () => {
    capture();
    const list = cfgDraft.config.workflow;
    const i = Number(b.dataset.i);
    if (b.dataset.node === 'add') list.push({ label: '研究复核', role: 'reviewer', mode: 'any', users: [] });
    if (b.dataset.node === 'remove' && list.length > 1) list.splice(i, 1);
    if (b.dataset.node === 'up' && i > 0) [list[i - 1], list[i]] = [list[i], list[i - 1]];
    if (b.dataset.node === 'down' && i < list.length - 1) [list[i + 1], list[i]] = [list[i], list[i + 1]];
    renderConfigForm(c);
  });
  c.querySelector('#category-form').onsubmit = event => {
    event.preventDefault();
    run(async () => {
      capture();
      await api('categories', { id: cfgDraft.id, revision: cfgDraft.revision, name: cfgDraft.name, config: cfgDraft.config, enabled: cfgDraft.enabled });
      await refresh();
      cfgDraft = null;
      renderCategories(c);
      toast('分类配置已保存');
    });
  };
  const capture = () => {
    const form = document.getElementById('category-form');
    const values = new FormData(form);
    const cfg2 = cfgDraft.config;
    cfgDraft.enabled = values.has('enabled') ? 1 : 0;
    for (const key of ['description', 'kind', 'title_pattern', 'header', 'footer', 'layout', 'color']) cfg2[key] = values.get(key);
    cfg2.font_size = Number(values.get('font_size') || 15);
    cfg2.commodities = String(values.get('commodities') || '').split(/[，,\n]/).map(x => x.trim()).filter(Boolean);
    cfg2.sections.forEach((s, i) => {
      s.title = values.get('sec-title-' + i) || s.title;
      s.default = values.get('sec-default-' + i) || '';
      s.type = values.get('sec-type-' + i) || '';
      s.required = values.has('sec-required-' + i);
      s.commodity_ids = values.getAll('sec-commodity-' + i).map(Number);
    });
    cfg2.workflow.forEach((n, i) => {
      n.label = values.get('node-label-' + i) || n.label;
      n.role = values.get('node-role-' + i);
      n.mode = values.get('node-mode-' + i);
      n.users = values.getAll('node-users-' + i).map(Number).filter(id => S().users.some(u => u.id === id && u.role === n.role));
    });
  };
}

export function renderAuthors(c) {
  renderCatalog(c, 'authors');
}

export function renderCommodities(c) {
  renderCatalog(c, 'commodities');
}

function renderCatalog(c, kind) {
  const author = kind === 'authors';
  const list = S()[kind] || [];
  c.innerHTML = `<div class="page-body"><div class="row spread page-head"><div><h2>${author ? '署名作者管理' : '研究品种管理'}</h2>
      <p class="caption">${author ? '署名作者与登录账号分别管理；停用不影响历史报告署名。' : '支持两级分类；停用后不能用于新建报告，历史引用保留。'}</p></div>
      <button class="primary" data-add>＋ 添加${author ? '作者' : '品种'}</button></div>
    <div class="panel"><div class="tablewrap"><table><thead><tr><th>名称</th><th>${author ? '适用报告类型' : '上级分类'}</th><th>状态</th><th>操作</th></tr></thead><tbody>
    ${list.map(x => `<tr><td>${esc(x.name)}</td><td>${author ? esc(JSON.parse(x.types).join('、')) : esc(S().commodities.find(p => p.id === x.parent_id)?.name || '一级')}</td>
      <td><span class="badge ${x.enabled ? 'green' : 'gray'}">${x.enabled ? '启用' : '停用'}</span></td>
      <td><button class="text-action" data-edit="${x.id}">编辑</button></td></tr>`).join('') || `<tr><td colspan="4" class="empty">暂无数据</td></tr>`}
    </tbody></table></div></div></div>`;
  c.querySelector('[data-add]').onclick = () => catalogDialog(kind, null, c);
  c.querySelectorAll('[data-edit]').forEach(b => b.onclick = () => catalogDialog(kind, Number(b.dataset.edit), c));
}

function catalogDialog(kind, id, host) {
  const author = kind === 'authors';
  const item = (S()[kind] || []).find(x => x.id === id);
  modal(`<form id="catalog-form"><label>名称<input name="name" required value="${esc(item?.name || '')}"></label>
    ${author ? `<label>适用类型（逗号分隔）<input name="types" required value="${esc(item ? JSON.parse(item.types).join('，') : '日报，周报，专题，调研纪要')}"></label>`
    : `<label>上级分类<select name="parent_id"><option value="">无 · 一级品种</option>${S().commodities.filter(p => !p.parent_id && p.id !== id).map(p => `<option value="${p.id}" ${item?.parent_id === p.id ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select></label>`}
    <label class="person inline"><input type="checkbox" name="enabled" ${!item || item.enabled ? 'checked' : ''}>启用</label>
    <div class="dialog-actions"><button type="button" data-close>取消</button><button class="primary">保存</button></div></form>`, { title: (id ? '编辑' : '添加') + (author ? '署名作者' : '研究品种') });
  document.getElementById('catalog-form').onsubmit = event => {
    event.preventDefault();
    const values = formObject(event.target);
    run(async () => {
      await api('catalog', { kind, id, name: values.name, types: author ? String(values.types).split(/[，,]/).map(x => x.trim()).filter(Boolean) : undefined, parent_id: values.parent_id ? Number(values.parent_id) : null, enabled: Boolean(values.enabled) });
      closeModal();
      await refresh();
      renderCatalog(host, kind);
      toast('已保存');
    });
  };
}

export function renderFlows(c) {
  const flows = S().flows || [];
  c.innerHTML = `<div class="page-body"><div class="row spread page-head"><div><h2>审批流配置</h2>
      <p class="caption">为指定分类设置多节点审批流；新建报告时按分类匹配并快照，未匹配则沿用分类自带的审批节点。</p></div>
      <button class="primary" data-add>＋ 添加审批流</button></div>
    <div class="panel"><div class="tablewrap"><table><thead><tr><th>名称</th><th>关联分类</th><th>节点</th><th>状态</th><th>操作</th></tr></thead><tbody>
    ${flows.map(f => `<tr><td>${esc(f.name)}</td>
      <td>${f.category_ids.map(id => esc(S().category_tree.find(n => n.id === id)?.name || '#' + id)).join('、') || '<span class="caption">全部分类</span>'}</td>
      <td>${f.nodes.map(n => esc(n.label) + '（' + MODE_NAMES[n.mode] + '）').join(' → ')} → 发布</td>
      <td><span class="badge ${f.enabled ? 'green' : 'gray'}">${f.enabled ? '启用' : '停用'}</span></td>
      <td class="row"><button class="text-action" data-edit="${f.id}">编辑</button><button class="text-action" data-del="${f.id}">删除</button></td></tr>`).join('') || '<tr><td colspan="5" class="empty">暂无审批流</td></tr>'}
    </tbody></table></div></div></div>`;
  c.querySelector('[data-add]').onclick = () => flowDialog(null, c);
  c.querySelectorAll('[data-edit]').forEach(b => b.onclick = () => flowDialog(S().flows.find(f => f.id === Number(b.dataset.edit)), c));
  c.querySelectorAll('[data-del]').forEach(b => b.onclick = () => run(async () => {
    await api('approval-flows', { action: 'delete', id: Number(b.dataset.del) });
    await refresh();
    renderFlows(c);
    toast('审批流已删除');
  }));
}

function flowDialog(flow, host) {
  const draft = flow ? JSON.parse(JSON.stringify(flow)) : { id: null, name: '', category_ids: [], nodes: [{ label: '研究复核', role: 'reviewer', mode: 'any', users: [] }], enabled: 1 };
  const paint = () => {
    modal(`<form id="flow-form"><label>审批流名称<input name="name" required maxlength="40" value="${esc(draft.name)}"></label>
      <p class="caption">关联分类（留空表示不生效，报告沿用分类配置里的审批节点）</p>
      <div class="row" style="max-height:120px;overflow:auto">${S().category_tree.filter(n => !n.folder).map(n => `<label class="person inline"><input type="checkbox" name="cats" value="${n.id}" ${draft.category_ids.includes(n.id) ? 'checked' : ''}>${esc(n.name)}</label>`).join('') || '<span class="caption">暂无末级分类</span>'}</div>
      <div class="row spread" style="margin-top:16px"><b>审批节点</b><button type="button" data-add-node>＋ 添加节点</button></div>
      ${draft.nodes.map((n, i) => `<div class="config-section"><div class="row spread"><b>节点 ${i + 1}</b><button type="button" data-del-node="${i}">删除</button></div>
        <div class="row"><label>名称<input name="label-${i}" value="${esc(n.label)}" style="width:120px"></label>
        <label>角色<select name="role-${i}"><option value="reviewer" ${n.role === 'reviewer' ? 'selected' : ''}>研究复核</option><option value="compliance" ${n.role === 'compliance' ? 'selected' : ''}>合规审核</option></select></label>
        <label>方式<select name="mode-${i}">${Object.entries(MODE_NAMES).map(([k, v]) => `<option value="${k}" ${n.mode === k ? 'selected' : ''}>${v}</option>`).join('')}</select></label></div>
        <label>指定审批人<select name="users-${i}" multiple size="2">${peopleOptions(n.role, n.users || [])}</select></label></div>`).join('')}
      <label class="person inline"><input type="checkbox" name="enabled" ${draft.enabled ? 'checked' : ''}>启用</label>
      <div class="dialog-actions"><button type="button" data-close>取消</button><button class="primary">保存</button></div></form>`, { title: flow ? '编辑审批流' : '添加审批流', wide: true });
    const form = document.getElementById('flow-form');
    const capture = () => {
      const values = new FormData(form);
      draft.name = values.get('name');
      draft.category_ids = values.getAll('cats').map(Number);
      draft.enabled = values.has('enabled') ? 1 : 0;
      draft.nodes.forEach((n, i) => {
        n.label = values.get('label-' + i) || n.label;
        n.role = values.get('role-' + i);
        n.mode = values.get('mode-' + i);
        n.users = values.getAll('users-' + i).map(Number).filter(id => S().users.some(u => u.id === id && u.role === n.role));
      });
    };
    form.querySelector('[data-add-node]').onclick = () => { capture(); draft.nodes.push({ label: '合规审核', role: 'compliance', mode: 'any', users: [] }); paint(); };
    form.querySelectorAll('[data-del-node]').forEach(b => b.onclick = () => { capture(); if (draft.nodes.length > 1) draft.nodes.splice(Number(b.dataset.delNode), 1); paint(); });
    form.onsubmit = event => {
      event.preventDefault();
      capture();
      run(async () => {
        await api('approval-flows', { action: flow ? 'update' : 'create', id: flow?.id, name: draft.name, category_ids: draft.category_ids, nodes: draft.nodes, enabled: draft.enabled });
        closeModal();
        await refresh();
        renderFlows(host);
        toast('审批流已保存');
      });
    };
  };
  paint();
}
