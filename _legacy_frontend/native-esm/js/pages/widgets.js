/* 研报列表等跨页面复用片段。 */
import { S } from '../core/api.js';
import { esc, statusText, STATUS_ORDER, localTime } from '../core/ui.js';

export function statusBadge(report) {
  const map = { '已发布': 'green', '已退回': 'red', '待发布': 'blue', '草稿': 'gray' };
  return `<span class="badge ${map[report.status] || 'amber'}">${esc(statusText(report))}</span>`;
}

export function isOwner(report) {
  return report.author === S().user.id || S().user.role === 'admin';
}

export function reportTable(reports, options = {}) {
  const rows = reports.map(report => {
    const meta = report.metadata ? JSON.parse(report.metadata) : null;
    const cfg = report.config_snapshot ? JSON.parse(report.config_snapshot) : null;
    const editable = report.author === S().user.id && ['草稿', '已退回'].includes(report.status);
    const category = cfg?.category_name || report.kind;
    const publishAt = localTime(report.published_at || report.approved_at);
    const updatedAt = localTime(report.updated);
    return `<tr>
      <td><button class="title-link" data-open="${report.id}" title="${esc(report.title)}">${esc(report.title)}</button></td>
      <td class="cell-clip" title="${esc(meta?.summary || '')}">${esc(meta?.summary || '—')}</td>
      <td title="${esc(category)}">${esc(category)}</td>
      <td>${esc(report.author_name)}</td>
      <td>${esc(report.updated_by || report.author_name)}</td>
      <td>${statusBadge(report)}</td>
      <td title="${esc(publishAt)}">${esc(publishAt)}</td>
      <td title="${esc(updatedAt)}">${esc(updatedAt)}</td>
      <td>第${report.issue || 1}期</td>
      <td>${report.views || 0}</td>
      <td class="cell-actions"><button class="text-action" data-open="${report.id}">${editable ? '编辑' : '查看'}</button><button class="text-action" data-more="${report.id}" aria-label="更多操作">···</button></td></tr>`;
  }).join('');
  // 列宽用百分比：1280/1440 等常见宽度都能自适应，窄屏只在 860px 以下出现横向滚动
  return `<div class="tablewrap"><table class="report-list"><colgroup>${[15, 8, 12.5, 6.5, 6.5, 7, 12, 12, 5.5, 3.5, 11].map(w => `<col style="width:${w}%">`).join('')}</colgroup>
    <thead><tr>${['报告标题', '摘要', '分类', '创建人', '更新人', '报告状态', '发布 / 审批时间', '更新时间', '期数', 'PV', '操作'].map(x => `<th>${x}</th>`).join('')}</tr></thead>
    <tbody>${rows || `<tr><td colspan="11" class="empty">暂无研报</td></tr>`}</tbody></table></div>`;
}

export function sortReports(list) {
  return [...list].sort((a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9) || String(b.updated).localeCompare(String(a.updated)));
}

export function bindReportTable(host, onOpen, onMore) {
  host.querySelectorAll('[data-open]').forEach(button => {
    button.onclick = () => onOpen(Number(button.dataset.open));
  });
  host.querySelectorAll('[data-more]').forEach(button => {
    button.onclick = () => onMore(Number(button.dataset.more));
  });
}
