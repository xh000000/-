/* 云盘 / 文档管理库 / 素材库：三级分类、上传、批量操作与大图预览。 */
import { S, api, refresh } from '../core/api.js';
import { esc, run, toast, modal, closeModal, formObject, empty, localTime } from '../core/ui.js';
import { actions } from '../core/actions.js';

let area = 'cloud';
let parentId = null;
const selectedIds = new Set();

const AREA_BY_PAGE = { '云盘': 'cloud', '文档管理库': 'docs', '素材库': 'materials' };
const TITLE = { cloud: '云盘', docs: '文档管理库', materials: '素材库' };

export function render(c, pageKey) {
  const next = AREA_BY_PAGE[pageKey] || 'cloud';
  if (next !== area) { area = next; parentId = null; selectedIds.clear(); }
  const items = S().library.filter(x => x.area === area && x.parent_id === parentId);
  const parent = S().library.find(x => x.id === parentId);
  const trail = [];
  let cursor = parent;
  while (cursor) { trail.unshift(cursor); cursor = S().library.find(x => x.id === cursor.parent_id); }
  const isMaterials = area === 'materials';

  const desc = isMaterials ? '素材库支持三级分类，可直接插入研报、预览与批量下载。'
    : area === 'docs' ? '文档在组织内共享，仅创建人与管理员可修改。'
      : '云盘用于存放文件，支持文件夹与批量下载。';
  c.innerHTML = `<div class="page-body">
    <div class="row spread page-head"><div><h2>${esc(TITLE[area])}</h2><p class="caption">${desc}</p></div>
      <div class="row"><button data-folder>新建文件夹</button>
        <button class="primary" data-new>${area === 'docs' ? '新建文档' : isMaterials ? '上传素材' : '上传文件'}</button></div></div>
    <div class="report-module">
    <div class="row library-toolbar">
      ${parentId ? '<button data-up>← 返回上级</button>' : ''}
      <span class="muted">当前位置：${trail.map(x => esc(x.name)).join(' / ') || '全部资料'}</span>
      <span class="row" style="margin-left:auto">
        <button data-batch="move" ${selectedIds.size ? '' : 'disabled'}>批量移动</button>
        <button data-batch="delete" ${selectedIds.size ? '' : 'disabled'}>批量删除</button>
        <button data-batch="zip" ${selectedIds.size ? '' : 'disabled'}>批量下载</button>
        <span class="caption" style="margin:0">已选 ${selectedIds.size} 项</span>
      </span>
    </div>
    ${isMaterials ? `<div class="lib-grid">${items.map(cardHTML).join('') || empty('暂无素材')}</div>` : `<div class="tablewrap"><table><thead><tr><th style="width:36px"><input type="checkbox" data-all ${items.length && items.every(x => selectedIds.has(x.id)) ? 'checked' : ''}></th><th>名称</th><th>类型</th><th>创建人</th><th>更新时间</th><th>操作</th></tr></thead>
      <tbody>${items.map(rowHTML).join('') || '<tr><td colspan="6" class="empty">暂无内容</td></tr>'}</tbody></table></div>`}
  </div></div>`;

  c.querySelector('[data-new]').onclick = () => uploadDialog(isMaterials ? 'image' : area === 'docs' ? 'document' : 'file');
  c.querySelector('[data-folder]').onclick = () => folderDialog();
  c.querySelector('[data-up]')?.addEventListener('click', () => { parentId = parent?.parent_id ?? null; selectedIds.clear(); render(c, pageKey); });
  c.querySelector('[data-all]')?.addEventListener('change', event => {
    items.forEach(x => event.target.checked ? selectedIds.add(x.id) : selectedIds.delete(x.id));
    render(c, pageKey);
  });
  c.querySelectorAll('[data-check]').forEach(box => box.onchange = () => {
    const id = Number(box.dataset.check);
    box.checked ? selectedIds.add(id) : selectedIds.delete(id);
    render(c, pageKey);
  });
  c.querySelectorAll('[data-open-folder]').forEach(b => b.onclick = () => { parentId = Number(b.dataset.openFolder); selectedIds.clear(); render(c, pageKey); });
  c.querySelectorAll('[data-edit]').forEach(b => b.onclick = () => editDialog(Number(b.dataset.edit), c, pageKey));
  c.querySelectorAll('[data-view]').forEach(b => b.onclick = () => lightbox(Number(b.dataset.view)));
  c.querySelectorAll('[data-batch]').forEach(b => b.onclick = () => batch(b.dataset.batch, c, pageKey));
  c.querySelectorAll('[data-download]').forEach(a => a.onclick = event => {
    event.preventDefault();
    window.open('/api/library/file/' + a.dataset.download + '?download=1', '_blank');
  });
}

function memberName(id) {
  return S().members.find(x => x.id === id)?.name || '#' + id;
}

function rowHTML(item) {
  const folder = item.kind === 'folder';
  return `<tr><td><input type="checkbox" data-check="${item.id}" ${selectedIds.has(item.id) ? 'checked' : ''}></td>
    <td>${folder ? `<button class="text-action" data-open-folder="${item.id}">📁 ${esc(item.name)}</button>` : esc(item.name)}</td>
    <td>${folder ? '文件夹' : item.kind === 'document' ? '文档' : item.mime || '文件'}</td>
    <td>${esc(memberName(item.owner))}</td><td>${esc(localTime(item.updated))}</td>
    <td class="row">${folder ? '' : item.kind === 'document' ? `<button class="text-action" data-edit="${item.id}">查看 / 编辑</button>` : `<a class="text-action" href="/api/library/file/${item.id}?download=1" data-download="${item.id}">下载</a>`}
      <button class="text-action" data-edit="${item.id}">${folder ? '重命名 / 移动' : '编辑'}</button></td></tr>`;
}

function cardHTML(item) {
  if (item.kind === 'folder') {
    return `<div class="lib-card"><button class="text-action" data-open-folder="${item.id}">📁 ${esc(item.name)}</button><div class="row"><button class="text-action" data-edit="${item.id}">编辑</button><input type="checkbox" data-check="${item.id}" ${selectedIds.has(item.id) ? 'checked' : ''}></div></div>`;
  }
  return `<div class="lib-card"><img src="/api/library/file/${item.id}" alt="${esc(item.name)}" data-view="${item.id}">
    <p>${esc(item.name)}</p><div class="row"><button class="text-action" data-view="${item.id}">查看大图</button>
    <a class="text-action" href="/api/library/file/${item.id}?download=1" data-download="${item.id}">下载</a>
    <input type="checkbox" data-check="${item.id}" ${selectedIds.has(item.id) ? 'checked' : ''}></div></div>`;
}

function lightbox(id) {
  const item = S().library.find(x => x.id === id);
  if (!item) return;
  modal(`<div class="dialog-body"><div class="lightbox"><img src="/api/library/file/${id}" alt="${esc(item.name)}"></div>
    <div class="row spread" style="margin-top:12px"><b>${esc(item.name)}</b><a class="text-action" href="/api/library/file/${id}?download=1">下载原图</a></div></div>`, { title: '素材预览', wide: true });
}

function folderDialog() {
  modal(`<form id="folder-form"><label>文件夹名称<input name="name" required maxlength="120"></label>
    <p class="caption">${area === 'materials' ? '素材库最多三级分类。' : '目录层级不限。'}</p>
    <div class="dialog-actions"><button type="button" data-close>取消</button><button class="primary">创建</button></div></form>`, { title: '新建文件夹' });
  document.getElementById('folder-form').onsubmit = event => {
    event.preventDefault();
    run(async () => {
      await api('library', { action: 'create', area, kind: 'folder', name: formObject(event.target).name, parent_id: parentId });
      closeModal();
      await refresh();
      render(document.getElementById('content'), Object.keys(AREA_BY_PAGE).find(k => AREA_BY_PAGE[k] === area));
      toast('文件夹已创建');
    });
  };
}

function uploadDialog(kind) {
  const isImage = kind === 'image';
  modal(`<form id="upload-form"><label>名称<input name="name" required maxlength="120"></label>
    ${kind === 'document' ? '<label>文档正文<textarea name="body" style="min-height:180px"></textarea></label>' : ''}
    ${kind !== 'document' ? `<label>选择${isImage ? '图片（PNG/JPEG/WebP）' : '文件'}<input type="file" name="file" ${isImage ? 'accept="image/png,image/jpeg,image/webp"' : ''} required></label>` : ''}
    <p class="caption">单个文件不超过 5MB。${isImage ? '素材可直接插入研报。' : ''}</p>
    <div class="dialog-actions"><button type="button" data-close>取消</button><button class="primary">上传</button></div></form>`, { title: kind === 'document' ? '新建文档' : isImage ? '上传素材' : '上传文件' });
  document.getElementById('upload-form').onsubmit = event => {
    event.preventDefault();
    const form = event.target;
    run(async () => {
      const values = formObject(form);
      const data = { action: 'create', area, kind, name: values.name || form.file?.files[0]?.name, parent_id: parentId, body: values.body || '' };
      const file = form.querySelector('input[type=file]')?.files[0];
      if (file) {
        if (file.size > 5000000) throw new Error('文件超过 5MB');
        data.base64 = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result).split(',')[1]);
          reader.onerror = reject;
          reader.readAsDataURL(file);
        });
        if (!data.name) data.name = file.name;
      }
      await api('library', data);
      closeModal();
      await refresh();
      render(document.getElementById('content'), Object.keys(AREA_BY_PAGE).find(k => AREA_BY_PAGE[k] === area));
      toast('已保存');
    });
  };
}

function editDialog(id, c, pageKey) {
  const item = S().library.find(x => x.id === id);
  if (!item) return;
  const editable = item.owner === S().user.id || S().user.role === 'admin';
  const folders = S().library.filter(x => x.area === area && x.kind === 'folder' && x.id !== id);
  modal(`<form id="lib-form"><label>名称<input name="name" required value="${esc(item.name)}" ${editable ? '' : 'readonly'}></label>
    <label>所在目录<select name="parent_id" ${editable ? '' : 'disabled'}><option value="">根目录</option>${folders.map(x => `<option value="${x.id}" ${item.parent_id === x.id ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}</select></label>
    ${item.kind === 'document' ? `<label>文档正文<textarea name="body" style="min-height:220px" ${editable ? '' : 'readonly'}>${esc(item.body || '')}</textarea></label>` : ''}
    ${item.kind === 'file' || item.kind === 'image' ? `<p class="caption"><a href="/api/library/file/${id}?download=1">下载该文件</a></p>` : ''}
    <div class="dialog-actions"><button type="button" data-close>取消</button>${editable ? `<button type="button" data-del>移除</button><button class="primary">保存</button>` : ''}</div></form>`, { title: '资料详情', wide: item.kind === 'document' });
  const form = document.getElementById('lib-form');
  form.querySelector('[data-del]')?.addEventListener('click', () => run(async () => {
    await api('library', { action: 'delete', item_id: id });
    closeModal();
    await refresh();
    render(c, pageKey);
    toast('已从列表移除');
  }));
  if (!editable) return;
  form.onsubmit = event => {
    event.preventDefault();
    const values = formObject(form);
    run(async () => {
      await api('library', { action: 'edit', item_id: id, name: values.name, parent_id: values.parent_id ? Number(values.parent_id) : null, body: values.body ?? item.body });
      closeModal();
      await refresh();
      render(c, pageKey);
      toast('已保存');
    });
  };
}

function batch(action, c, pageKey) {
  const ids = [...selectedIds];
  if (!ids.length) return toast('请先勾选资料');
  if (action === 'zip') {
    window.open('/api/library/zip?ids=' + ids.join(','), '_blank');
    return;
  }
  if (action === 'delete') {
    run(async () => {
      await api('library/batch', { action: 'delete', ids });
      selectedIds.clear();
      await refresh();
      render(c, pageKey);
      toast('已移除 ' + ids.length + ' 项');
    });
    return;
  }
  const folders = S().library.filter(x => x.area === area && x.kind === 'folder' && !ids.includes(x.id));
  modal(`<form id="move-form"><label>移动到<select name="parent_id"><option value="">根目录</option>${folders.map(x => `<option value="${x.id}">${esc(x.name)}</option>`).join('')}</select></label>
    <div class="dialog-actions"><button type="button" data-close>取消</button><button class="primary">移动</button></div></form>`, { title: '批量移动（' + ids.length + ' 项）' });
  document.getElementById('move-form').onsubmit = event => {
    event.preventDefault();
    const values = formObject(event.target);
    run(async () => {
      await api('library/batch', { action: 'move', ids, parent_id: values.parent_id ? Number(values.parent_id) : null });
      closeModal();
      selectedIds.clear();
      await refresh();
      render(c, pageKey);
      toast('已移动');
    });
  };
}
