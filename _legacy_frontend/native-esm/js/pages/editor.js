/* 研报编辑器：章节 + 组件（文字/图表/表格/图片）、章节协作、三种布局与版本保存。 */
import { S, api, refresh } from '../core/api.js';
import { esc, run, toast, modal, closeModal, formObject, statusText, empty, localTime, today } from '../core/ui.js';
import { actions } from '../core/actions.js';
import { iconSVG } from '../core/menu.js';

let draft = null, draftId = null, draftVersion = 0, draftTitle = '', chapterIndex = 0, backToList = null;
let savedSnapshot = '', dragged = null;

const clone = value => JSON.parse(JSON.stringify(value));
const makeId = () => (crypto.randomUUID ? crypto.randomUUID() : 'b-' + Date.now() + '-' + Math.random().toString(16).slice(2));
const canEditStatus = report => ['草稿', '已退回'].includes(report.status);

function initDraft(report, force = false) {
  if (!force && draftId === report.id && draftVersion === report.version) return;
  const sameReport = draftId === report.id;
  draft = JSON.parse(report.document);
  draftTitle = report.title;
  draftId = report.id;
  draftVersion = report.version;
  if (!sameReport || chapterIndex >= draft.sections.length) chapterIndex = 0;
  savedSnapshot = JSON.stringify({ title: draftTitle, doc: draft });
}

function capture() {
  if (!draft) return;
  const title = document.getElementById('report-title');
  if (title) draftTitle = title.value;
  document.querySelectorAll('[data-block-text]').forEach(el => {
    const block = draft.sections[Number(el.dataset.section)]?.blocks[Number(el.dataset.blockText)];
    if (!block) return;
    if (el.dataset.rich === '1') {
      block.html = el.innerHTML;
      block.text = el.innerText;
    } else {
      block.text = el.value;
    }
  });
  document.querySelectorAll('[data-block-title]').forEach(el => {
    const block = draft.sections[Number(el.dataset.section)]?.blocks[Number(el.dataset.blockTitle)];
    if (block) block.title = el.value;
  });
}

export function unsavedMessage() {
  if (!draft) return '';
  capture();
  return JSON.stringify({ title: draftTitle, doc: draft }) === savedSnapshot ? '' : '存在未保存修改，请先保存';
}

function chapterEditable(report, section) {
  const meta = report.metadata ? JSON.parse(report.metadata) : null;
  if (!canEditStatus(report)) return false;
  if (!meta || meta.collaboration !== 'shared') return report.author === S().user.id;
  return section.state !== '已提交' && section.editors.includes(S().user.id);
}

function chartSVG(block) {
  const rows = (block.data || []).slice(-60);
  if (!rows.length) return '<p class="empty">保存后由服务端生成数据快照</p>';
  const values = rows.map(r => Number(r.value));
  let low = Math.min(...values), high = Math.max(...values);
  if (low === high) { low -= 1; high += 1; }
  const points = rows.map((r, i) => `${50 + i * 480 / Math.max(1, rows.length - 1)},${175 - (r.value - low) / (high - low) * 135}`).join(' ');
  return `<svg viewBox="0 0 580 215" width="100%" role="img" aria-label="${esc(block.indicator)}时间序列图">
    <line x1="50" y1="175" x2="530" y2="175" stroke="#cfdde3"></line><line x1="50" y1="40" x2="50" y2="175" stroke="#cfdde3"></line>
    <text x="4" y="45" font-size="10" fill="#78909c">${esc(high.toFixed(2))}</text><text x="4" y="178" font-size="10" fill="#78909c">${esc(low.toFixed(2))}</text>
    <polyline points="${points}" fill="none" stroke="#0758d8" stroke-width="2.5"></polyline>
    <text x="50" y="198" font-size="10" fill="#78909c">${esc(rows[0].date)}</text><text x="460" y="198" font-size="10" fill="#78909c">${esc(rows[rows.length - 1].date)}</text></svg>`;
}

function dataHTML(block) {
  if (!block.data || !block.data.length) return '<p class="empty">保存后自动获取数据快照</p>';
  const table = `<div class="tablewrap"><table><tr><th>日期</th><th>${esc(block.indicator)}</th><th>单位</th></tr>${block.data.slice(-12).map(r => `<tr><td>${esc(r.date)}</td><td>${esc(r.value)}</td><td>${esc(r.unit)}</td></tr>`).join('')}</table></div>`;
  return `${block.type === 'chart' ? chartSVG(block) : table}<p class="caption">来源：${esc(block.source)} · ${esc(block.indicator)} · 快照 ${block.data.length} 条 · 刷新于 ${esc(block.refreshed_at || '')}</p>`;
}

function blockHTML(report, block, si, bi, readonly = false) {
  const editable = !readonly && chapterEditable(report, draft.sections[si]);
  const free = draft.layout === 'free';
  const style = free ? ` style="left:${block.x ?? 30}px;top:${block.y ?? 70 + bi * 230}px;width:${block.width ?? 620}px;height:${block.height ?? 210}px"` : '';
  const top = editable ? `<div class="component-top"><span>${free ? '⠿ ' : ''}${esc(block.title || ({ text: '文字组件', chart: '指标图表', table: '数据表格', image: '图片' }[block.type]))}</span>
      <span><button data-block-act="up" data-si="${si}" data-bi="${bi}" aria-label="上移">↑</button>
      <button data-block-act="down" data-si="${si}" data-bi="${bi}" aria-label="下移">↓</button>
      <button data-block-act="span" data-si="${si}" data-bi="${bi}">${block.span === 6 ? '半宽' : '整宽'}</button>
      <button data-block-act="remove" data-si="${si}" data-bi="${bi}">×</button></span></div>` : (block.title ? `<b>${esc(block.title)}</b>` : '');
  const body = block.type === 'text'
    ? `<div class="rich-area" ${editable ? `contenteditable="true" data-rich="1" data-block-text="${bi}" data-section="${si}"` : ''}>${block.html ?? esc(block.text || '').replaceAll('\n', '<br>')}</div>`
    : block.type === 'image'
      ? `<img alt="${esc(block.asset_name || '')}" src="/api/library/file/${Number(block.asset_id)}" style="max-width:100%;height:auto">`
      : dataHTML(block);
  return `<article class="rich-block ${free ? 'free-element' : ''} ${draft.layout === 'grid' && block.span === 6 ? 'half' : ''}" data-drop="${bi}" data-free="${free ? bi : ''}" data-si="${si}"${style}>${top}${body}</article>`;
}

function chapterHTML(report, section, si) {
  const editable = chapterEditable(report, section);
  const grid = draft.layout === 'grid' ? 'canvas-grid' : '';
  return `<h3>${esc(section.title)}${section.required ? ' <span class="caption">必填</span>' : ''}</h3>
    <div class="${grid}">${section.blocks.map((block, bi) => blockHTML(report, block, si, bi)).join('') || '<p class="empty">当前章节暂无组件，从工具栏插入文字、图表、表格或图片。</p>'}</div>`;
}

export function render(c, id, onBack) {
  const report = S().reports.find(r => r.id === id);
  if (!report) { c.innerHTML = empty('报告不存在或无权访问'); return; }
  backToList = onBack;
  if (!report.document) return renderLegacy(c, report);
  initDraft(report);
  const cfg = report.config_snapshot ? JSON.parse(report.config_snapshot) : {};
  const meta = report.metadata ? JSON.parse(report.metadata) : null;
  const shared = meta?.collaboration === 'shared';
  const edit = canEditStatus(report) && (shared ? true : report.author === S().user.id);
  const section = draft.sections[chapterIndex];
  const allowed = report.allowed_actions || [];
  const creator = report.author === S().user.id;

  c.innerHTML = `<div class="edit-top"><div class="row"><button data-back>‹ 返回</button><strong>${esc(draftTitle)}</strong>
      <span class="badge">${esc(statusText(report))} · v${report.version}</span></div>
    <div class="edit-actions">
      <button data-act="info">基础信息</button>
      <button data-act="preview">预览</button>
      <button data-act="print">打印 / PDF</button>
      ${report.can_schedule ? '<button data-act="schedule">定时发布</button>' : ''}
      ${allowed.map(a => `<button data-trans="${esc(a)}">${a === '提交' ? '提交审批' : a === '通过' ? '审核通过' : a === '退回' ? '退回' : a === '发布' ? '发布' : esc(a)}</button>`).join('')}
    </div></div>
  <div class="edit-layout"><div class="chapter-list">
      <div class="row spread"><b>研报章节</b>${creator && edit ? '<button class="primary" data-chapter-add>添加章节</button>' : ''}</div>
      ${draft.sections.map((x, i) => `<div class="chapter-card ${i === chapterIndex ? 'active' : ''}"><button class="title-link" data-chapter="${i}">${x.type ? `<span class="chapter-type">${esc(x.type)}</span>` : ''}<b>${esc(x.title)}</b></button>
        <div class="chapter-card-foot"><span>${esc(x.state || '未提交')}</span><span>${creator && edit ? `<button class="text-action icon-action" data-chapter-settings="${i}" title="章节设置">${iconSVG('gear')}</button>` : ''}</span></div>
        <div class="caption">${x.editors.map(id2 => esc(memberName(id2))).join('、')}</div></div>`).join('')}
    </div>
    <div class="chapter-editor">
      <div class="chapter-top"><h3>${esc(section.title)}</h3><div class="edit-actions"><span class="chapter-badge">${esc(section.state || '未提交')} · 本章 v${section.revision}</span>
        ${chapterEditable(report, section) ? '<button data-act="clear">一键清空</button><button data-act="refresh">↻ 刷新数据并保存</button><button data-act="save">保存本章</button>' : ''}
        ${shared && edit ? '<button data-act="submit-chapter">提交章节</button>' : ''}
        ${shared && edit && section.state === '已提交' ? '<button data-act="reopen">撤销提交</button>' : ''}</div></div>
      <div class="canvas-toolbar">
        <label>报告标题 <input id="report-title" value="${esc(draftTitle)}" ${edit ? '' : 'readonly'} style="width:320px"></label>
        <span class="row">${chapterEditable(report, section) ? '<button data-insert="text">＋ 文字</button><button data-insert="chart">＋ 指标图表</button><button data-insert="table">＋ 数据表格</button><button data-insert="image">＋ 图片</button>' : '<span class="caption">本章节不可编辑（已提交或未分配给你）</span>'}</span>
        ${chapterEditable(report, section) ? `<span class="row"><button data-format="bold"><b>B</b></button><button data-format="italic"><i>I</i></button><button data-format="underline"><u>U</u></button><button data-format="insertUnorderedList">•</button></span>` : ''}
        ${chapterEditable(report, section) ? '<button data-act="ai">AI 生成本章候选</button>' : ''}
      </div>
      <div class="canvas-paper ${draft.layout === 'free' ? 'free-paper' : ''}" id="chapter-content">${chapterHTML(report, section, chapterIndex)}</div>
    </div>${chapterEditable(report, section) ? `<div class="resource-strip">${[['text', 'doc', '文字'], ['chart', 'chart', '图表'], ['table', 'table', '表格'], ['image', 'image', '图片']].map(([kind, icon, label]) => `<button data-insert="${kind}"><span class="resource-symbol">${iconSVG(icon)}</span>${label}</button>`).join('')}</div>` : ''}</div>`;

  bind(c, report, section, shared, edit);
}

function memberName(id) {
  return S().members.find(x => x.id === id)?.name || '#' + id;
}

function bind(c, report, section, shared, edit) {
  c.querySelector('[data-back]').onclick = () => {
    const warn = unsavedMessage();
    if (warn) return toast(warn);
    draft = null; draftId = null;
    backToList?.();
  };
  c.querySelectorAll('[data-chapter]').forEach(button => button.onclick = () => {
    const warn = unsavedMessage();
    if (warn) return toast(warn);
    capture();
    chapterIndex = Number(button.dataset.chapter);
    actions.refreshPage?.();
  });
  c.querySelectorAll('[data-chapter-settings]').forEach(button => button.onclick = event => {
    event.stopPropagation();
    chapterSettings(Number(button.dataset.chapter));
  });
  c.querySelector('[data-chapter-add]')?.addEventListener('click', () => chapterStructure('add'));
  c.querySelectorAll('[data-trans]').forEach(button => button.onclick = () => transition(report, button.dataset.trans));
  c.querySelector('[data-act="info"]').onclick = () => reportInfo(report);
  c.querySelector('[data-act="preview"]').onclick = () => preview(report);
  c.querySelector('[data-act="print"]').onclick = () => window.open('/api/report-print/' + report.id, '_blank');
  c.querySelector('[data-act="schedule"]')?.addEventListener('click', () => schedule(report));
  c.querySelector('[data-act="save"]')?.addEventListener('click', () => save(report, shared, false));
  c.querySelector('[data-act="refresh"]')?.addEventListener('click', () => save(report, shared, true));
  c.querySelector('[data-act="submit-chapter"]')?.addEventListener('click', () => chapterState('submit', report));
  c.querySelector('[data-act="reopen"]')?.addEventListener('click', () => chapterState('reopen', report));
  c.querySelector('[data-act="clear"]')?.addEventListener('click', () => {
    capture();
    draft.sections[chapterIndex].blocks = [];
    actions.refreshPage?.();
  });
  c.querySelector('[data-act="ai"]')?.addEventListener('click', event => generate(report, section, event.target));
  c.querySelectorAll('[data-insert]').forEach(button => button.onclick = () => insert(button.dataset.insert));
  c.querySelectorAll('[data-format]').forEach(button => button.onmousedown = event => {
    event.preventDefault();
    document.execCommand(button.dataset.format, false, null);
  });
  c.querySelectorAll('[data-block-act]').forEach(button => button.onclick = () => blockAction(Number(button.dataset.si), Number(button.dataset.bi), button.dataset.blockAct));
  c.querySelectorAll('[contenteditable=true]').forEach(el => {
    el.onpaste = event => {
      event.preventDefault();
      document.execCommand('insertText', false, event.clipboardData.getData('text/plain'));
    };
  });
  if (draft.layout === 'free' && edit) {
    c.querySelectorAll('[data-free]').forEach(el => {
      if (!el.dataset.free) return;
      const bar = el.querySelector('.component-top');
      if (!bar) return;
      bar.onpointerdown = event => {
        if (event.target.closest('button')) return;
        capture();
        const si = Number(el.dataset.si), bi = Number(el.dataset.free);
        const block = draft.sections[si].blocks[bi];
        const startX = event.clientX, startY = event.clientY, x = block.x ?? 30, y = block.y ?? 70;
        bar.setPointerCapture(event.pointerId);
        bar.onpointermove = move => {
          block.x = Math.max(0, Math.min(760 - (block.width || 620), x + move.clientX - startX));
          block.y = Math.max(0, Math.min(40000, y + move.clientY - startY));
          el.style.left = block.x + 'px';
          el.style.top = block.y + 'px';
        };
        bar.onpointerup = () => { bar.onpointermove = null; };
      };
      el.onpointerup = () => {
        const block = draft.sections[Number(el.dataset.si)].blocks[Number(el.dataset.free)];
        block.width = Math.max(120, el.offsetWidth);
        block.height = Math.max(80, el.offsetHeight);
        el.style.width = block.width + 'px';
        el.style.height = block.height + 'px';
      };
    });
  }
}

function blockAction(si, bi, action) {
  capture();
  const list = draft.sections[si].blocks;
  if (action === 'remove') list.splice(bi, 1);
  if (action === 'span') list[bi].span = list[bi].span === 6 ? 12 : 6;
  if (action === 'up' && bi > 0) [list[bi - 1], list[bi]] = [list[bi], list[bi - 1]];
  if (action === 'down' && bi < list.length - 1) [list[bi + 1], list[bi]] = [list[bi], list[bi + 1]];
  actions.refreshPage?.();
}

function insert(type) {
  capture();
  if (type === 'image') return pickImage();
  if (type === 'text') {
    draft.sections[chapterIndex].blocks.push({ id: makeId(), type: 'text', span: 12, title: '', text: '' });
    return actions.refreshPage?.();
  }
  const items = S().indicators || [];
  if (!items.length) return toast('尚无指标，请先在数据中心导入 CSV');
  modal(`<form id="data-picker"><label>选择指标<select name="index">${items.map((r, i) => `<option value="${i}">${esc(r.source)} / ${esc(r.indicator)} · ${esc(r.unit)} · 最新 ${esc(r.latest)}</option>`).join('')}</select></label>
    <p class="caption">保存时由服务端生成数据快照，之后可「刷新数据并保存」更新。</p>
    <div class="dialog-actions"><button type="button" data-close>取消</button><button class="primary">插入当前章节</button></div></form>`, { title: type === 'chart' ? '插入指标图表' : '插入数据表格' });
  document.getElementById('data-picker').onsubmit = event => {
    event.preventDefault();
    const item = items[Number(formObject(event.target).index)];
    draft.sections[chapterIndex].blocks.push({ id: makeId(), type, span: 12, title: item.indicator, source: item.source, indicator: item.indicator, data: [], refreshed_at: '待保存时获取' });
    closeModal();
    actions.refreshPage?.();
    toast('已插入引用，保存后加载数据');
  };
}

function pickImage() {
  const items = S().library.filter(x => x.kind === 'image');
  if (!items.length) return toast('素材库暂无图片，请先在素材库上传');
  modal(`<div class="lib-grid">${items.map(x => `<div class="lib-card"><img src="/api/library/file/${x.id}" alt="${esc(x.name)}"><p>${esc(x.name)}</p><button data-pick="${x.id}">插入</button></div>`).join('')}</div>`, { title: '素材库 · 插入图片', wide: true });
  document.querySelectorAll('[data-pick]').forEach(button => button.onclick = () => {
    capture();
    const item = items.find(x => x.id === Number(button.dataset.pick));
    draft.sections[chapterIndex].blocks.push({ id: makeId(), type: 'image', span: 12, title: item.name, asset_id: item.id, asset_name: item.name });
    closeModal();
    actions.refreshPage?.();
  });
}

async function save(report, shared, refreshData) {
  await run(async () => {
    capture();
    if (report.metadata && JSON.parse(report.metadata).collaboration === 'shared') {
      const section = draft.sections[chapterIndex];
      await api('chapter/save', { id: report.id, section_id: section.id, revision: section.revision, blocks: section.blocks, refresh: refreshData });
    } else {
      await api('personal-save', { id: report.id, version: report.version, document: draft, refresh: refreshData });
    }
    await refresh();
    const fresh = S().reports.find(r => r.id === report.id);
    initDraft(fresh, true);
    actions.refreshPage?.();
    toast(refreshData ? '数据已刷新并保存' : '已保存');
  });
}

async function chapterState(action, report) {
  await run(async () => {
    const warn = unsavedMessage();
    if (warn) throw new Error('请先保存本章');
    const section = draft.sections[chapterIndex];
    await api('chapter/' + action, { id: report.id, section_id: section.id, revision: section.revision });
    await refresh();
    initDraft(S().reports.find(r => r.id === report.id), true);
    actions.refreshPage?.();
    toast(action === 'submit' ? '章节已提交并锁定' : '已撤销提交');
  });
}

async function chapterStructure(action, payload = {}) {
  const report = S().reports.find(r => r.id === draftId);
  await run(async () => {
    if (unsavedMessage()) throw new Error('请先保存当前章节');
    const section = draft.sections[chapterIndex];
    await api('chapters', { id: report.id, version: report.version, section_id: section.id, action, ...payload });
    closeModal();
    await refresh();
    initDraft(S().reports.find(r => r.id === report.id), true);
    actions.refreshPage?.();
    toast('章节结构已更新');
  });
}

function chapterSettings(index) {
  const report = S().reports.find(r => r.id === draftId);
  const meta = report.metadata ? JSON.parse(report.metadata) : null;
  const section = draft.sections[index];
  const people = [report.author, ...(meta?.collaborators || [])];
  modal(`<form id="chapter-form"><label>章节名称<input name="title" required value="${esc(section.title)}"></label>
    <p class="caption">章节编辑人</p>${people.map(id => `<label class="person inline"><input type="checkbox" name="editors" value="${id}" ${section.editors.includes(id) ? 'checked' : ''}>${esc(memberName(id))}</label>`).join('')}
    <label>章节标签（逗号分隔）<input name="tags" value="${esc((section.tags || []).join('，'))}"></label>
    <p class="caption">关联品种</p>${S().commodities.filter(x => x.enabled).map(x => `<label class="person inline"><input type="checkbox" name="commodity_ids" value="${x.id}" ${(section.commodity_ids || []).includes(x.id) ? 'checked' : ''}>${esc(x.name)}</label>`).join('')}
    <div class="dialog-actions"><button type="button" data-close>取消</button><button type="button" data-structure="up">上移</button><button type="button" data-structure="down">下移</button><button type="button" data-structure="remove">移除</button><button class="primary">保存设置</button></div></form>`, { title: '章节基础信息' });
  document.getElementById('chapter-form').onsubmit = event => {
    event.preventDefault();
    const form = new FormData(event.target);
    chapterIndex = index;
    chapterStructure('edit', {
      title: form.get('title'), editors: form.getAll('editors').map(Number),
      tags: String(form.get('tags') || '').split(/[，,]/).map(x => x.trim()).filter(Boolean),
      commodity_ids: form.getAll('commodity_ids').map(Number),
    });
  };
  document.querySelectorAll('[data-structure]').forEach(button => button.onclick = () => {
    chapterIndex = index;
    chapterStructure(button.dataset.structure);
  });
}

function reportInfo(report) {
  const meta = report.metadata ? JSON.parse(report.metadata) : null;
  const editable = report.author === S().user.id && canEditStatus(report);
  modal(`<form id="info-form"><p class="caption">分类、新增方式、协作方式、布局在创建后锁定。</p>
    <label>标题<input name="title" required value="${esc(report.title)}" ${editable ? '' : 'readonly'}></label>
    <label>摘要<textarea name="summary" style="min-height:80px" ${editable ? '' : 'readonly'}>${esc(meta?.summary || '')}</textarea></label>
    <label>署名作者<select name="byline_id" ${editable ? '' : 'disabled'}>${S().authors.filter(a => (a.enabled && JSON.parse(a.types).includes(report.kind)) || a.id === meta?.byline_id).map(a => `<option value="${a.id}" ${a.id === meta?.byline_id ? 'selected' : ''}>${esc(a.name)}</option>`).join('')}</select></label>
    <label>创建日期<input type="date" name="report_date" value="${esc(meta?.report_date || today())}" ${editable ? '' : 'readonly'}></label>
    <label>公开发布<select name="public" ${editable ? '' : 'disabled'}><option value="true" ${meta?.public ? 'selected' : ''}>发布后公开</option><option value="false" ${meta?.public ? '' : 'selected'}>非公开</option></select></label>
    <div class="dialog-actions"><button type="button" data-close>关闭</button>${editable ? '<button class="primary">保存</button>' : ''}</div></form>`, { title: '报告基础信息' });
  const form = document.getElementById('info-form');
  form.onsubmit = event => {
    event.preventDefault();
    run(async () => {
      if (unsavedMessage()) throw new Error('请先关闭弹窗并保存当前章节');
      const values = formObject(event.target);
      await api('report-info', { id: report.id, version: report.version, title: values.title, summary: values.summary, byline_id: Number(values.byline_id), report_date: values.report_date, public: values.public === 'true' });
      closeModal();
      await refresh();
      initDraft(S().reports.find(r => r.id === report.id), true);
      actions.refreshPage?.();
      toast('基础信息已保存');
    });
  };
}

function preview(report) {
  capture();
  const cfg = report.config_snapshot ? JSON.parse(report.config_snapshot) : {};
  const meta = report.metadata ? JSON.parse(report.metadata) : null;
  modal(`<div class="dialog-body"><div class="row spread"><h3>${esc(draftTitle)}</h3><button onclick="window.print()">打印 / 保存 PDF</button></div>
    <p class="caption">${esc(report.commodity)} · ${esc(report.kind)} · 署名 ${esc(meta?.byline || report.author_name)} · ${esc(meta?.report_date || '')}</p>
    <div class="canvas-paper ${draft.layout === 'free' ? 'free-paper' : ''}" style="--theme:${cfg.color || '#409EFF'}">
      <div class="paper-head">${esc(cfg.header || '')}</div>
      ${draft.sections.map((section, si) => `<h3>${esc(section.title)}</h3><div class="${draft.layout === 'grid' ? 'canvas-grid' : ''}">${section.blocks.map((block, bi) => blockHTML(report, block, si, bi, true)).join('')}</div>`).join('')}
      <div class="paper-foot">${esc(cfg.footer || '')}</div></div></div>`, { title: '报告预览', wide: true, plain: false });
}

function schedule(report) {
  modal(`<form id="sch-form"><label>定时发布时间<input type="datetime-local" name="at" required></label>
    <p class="caption">到点由服务端自动发布并写入操作留痕。</p>
    <div class="dialog-actions"><button type="button" data-close>取消</button><button class="primary">保存</button></div></form>`, { title: '定时发布' });
  document.getElementById('sch-form').onsubmit = event => {
    event.preventDefault();
    run(async () => {
      await api('report-schedule', { id: report.id, at: formObject(event.target).at });
      closeModal();
      await refresh();
      actions.refreshPage?.();
      toast('已设置定时发布');
    });
  };
}

function transition(report, action) {
  const needNote = action === '退回';
  modal(`<form id="trans-form">${needNote ? '<label>退回原因<textarea name="note" required style="min-height:90px"></textarea></label>' : ''}
    <p class="caption">当前状态：${esc(statusText(report))}；操作会绑定当前版本。</p>
    <div class="dialog-actions"><button type="button" data-close>取消</button><button class="primary">确认${esc(action)}</button></div></form>`, { title: '流程操作' });
  document.getElementById('trans-form').onsubmit = event => {
    event.preventDefault();
    run(async () => {
      if (unsavedMessage()) throw new Error('请先保存修改，再操作流程');
      await api('transition', { id: report.id, action, note: formObject(event.target).note || '', expected_status: report.status, expected_workflow: report.workflow_state });
      closeModal();
      await refresh();
      actions.refreshPage?.();
      toast('流程已更新');
    });
  };
}

async function generate(report, section, button) {
  await run(async () => {
    capture();
    button.disabled = true;
    try {
      const result = await api('generate', { id: report.id, section_id: section.id });
      const block = draft.sections[chapterIndex].blocks.find(b => b.type === 'text');
      if (!block) throw new Error('请先插入一个文字组件');
      block.text = result.body;
      block.html = esc(result.body).replaceAll('\n', '<br>');
      actions.refreshPage?.();
      toast('候选内容已生成，核验后请保存');
    } finally {
      button.disabled = false;
    }
  });
}

function renderLegacy(c, report) {
  const editable = report.author === S().user.id && canEditStatus(report);
  c.innerHTML = `<div class="page-body"><div class="panel">
    <div class="row spread"><button data-back>‹ 返回</button><span class="badge">${esc(statusText(report))} · v${report.version}</span></div>
    <div class="warning">此报告为旧版纯文本正文，可继续使用，或转换为组件文档后按章节协作。</div>
    <label>报告标题<input id="legacy-title" value="${esc(report.title)}" ${editable ? '' : 'disabled'}></label>
    <textarea id="legacy-body" style="min-height:420px" ${editable ? '' : 'readonly'}>${esc(report.body)}</textarea>
    <div class="row">${editable ? '<button class="primary" data-save>保存版本</button><button data-convert>转换为组件文档</button><button data-submit>提交审批</button>' : ''}
      <button data-check>规则检查</button><button data-history>版本留痕</button><button data-print>打印 / PDF</button></div>
    <div id="legacy-checks" class="panel"></div></div></div>`;
  c.querySelector('[data-back]').onclick = () => { draft = null; backToList?.(); };
  c.querySelector('[data-print]').onclick = () => window.open('/api/report-print/' + report.id, '_blank');
  c.querySelector('[data-save]')?.addEventListener('click', () => run(async () => {
    await api('save', { id: report.id, version: report.version, title: document.getElementById('legacy-title').value, body: document.getElementById('legacy-body').value });
    await refresh();
    actions.refreshPage?.();
    toast('版本已保存');
  }));
  c.querySelector('[data-convert]')?.addEventListener('click', () => run(async () => {
    await api('convert', { id: report.id });
    await refresh();
    actions.refreshPage?.();
    toast('已转换为组件文档');
  }));
  c.querySelector('[data-submit]')?.addEventListener('click', () => run(async () => {
    await api('transition', { id: report.id, action: '提交' });
    await refresh();
    actions.refreshPage?.();
    toast('已提交审批');
  }));
  c.querySelector('[data-check]').onclick = () => run(async () => {
    const result = await api('check', { id: report.id });
    document.getElementById('legacy-checks').innerHTML = result.checks.map(x => `<p><span class="badge">${esc(x.level)}</span> ${esc(x.message)}</p>`).join('');
  });
  c.querySelector('[data-history]').onclick = () => run(async () => {
    const data = await api('history/' + report.id);
    modal(`<h3>操作记录</h3>${data.events.map(e => `<p><b>${esc(e.actor)} · ${esc(e.action)}</b> · v${e.version}<br><span class="caption">${esc(localTime(e.at))}</span><br>${esc(e.note)}</p>`).join('')}
      <h3>历史版本</h3>${data.versions.map(v => `<details><summary>v${v.version} · ${esc(v.actor)} · ${esc(localTime(v.at))}</summary><pre style="white-space:pre-wrap">${esc(v.body)}</pre></details>`).join('')}`, { title: '版本与留痕', wide: true });
  });
}
