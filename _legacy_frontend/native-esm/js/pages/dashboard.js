/* 工作台：数据概览 + 研报流程指引。 */
import { S } from '../core/api.js';
import { esc, statusText } from '../core/ui.js';
import { reportTable, bindReportTable, sortReports } from './widgets.js';
import * as reports from './reports.js';

export function render(c) {
  const list = S().reports;
  const cards = [['研究报告', list.length], ['审核处理中', list.filter(r => ['研究复核', '合规审核'].includes(r.status)).length],
    ['已发布', list.filter(r => r.status === '已发布').length], ['数据记录', S().data.length + (S().data.length === 500 ? '+' : '')]];
  c.innerHTML = `<div class="page-body">
    <div class="cards">${cards.map(([label, value]) => `<div class="card"><span class="muted">${label}</span><b>${value}</b></div>`).join('')}</div>
    <div class="warning">数据接入：当前支持授权导出后的 CSV 导入与手工录入，实时行情接口尚未接通。AI：${S().ai ? '已配置外部模型' : '未配置外部模型'}。</div>
    <div class="steps">${['① 数据入库', '② 研究撰写', '③ 研究复核', '④ 合规审核', '⑤ 内部发布', '⑥ 知识沉淀'].map(x => `<span>${x}</span>`).join('')}</div>
    <div class="panel"><div class="row spread"><h3>近期研究</h3><button class="primary" data-new>＋ 新建研报</button></div>
    <div id="dash-list">${reportTable(sortReports(list).slice(0, 8))}</div></div></div>`;
  c.querySelector('[data-new]').onclick = () => reports.newReport();
  bindReportTable(c.querySelector('#dash-list'), id => reports.open(id), id => reports.more(id));
}
