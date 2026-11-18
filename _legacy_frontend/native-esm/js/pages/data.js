/* 数据中心：CSV 导入、已入库指标与最近数据记录。 */
import { S, api, refresh } from '../core/api.js';
import { esc, run, toast, empty } from '../core/ui.js';

export function render(c) {
  const indicators = S().indicators || [];
  c.innerHTML = `<div class="page-body">
    <div class="row spread page-head"><div><h2>手工数据录入</h2>
      <p class="caption">当前支持授权导出后的 CSV 导入与手工录入；实时行情接口尚未接通，导入前请确认数据使用授权。</p></div></div>
    <div class="cards source-cards"><div class="card"><h3>Wind</h3><span class="badge">文件导入可用</span><p class="caption">实时接口未连接；需确认产品与数据使用授权。</p></div>
      <div class="card"><h3>同花顺</h3><span class="badge">文件导入可用</span><p class="caption">实时接口未连接；需确认 iFinD 等具体产品授权。</p></div></div>
    <div class="panel"><h3>导入研究数据</h3>
      <p class="caption">UTF-8 CSV，表头 source,indicator,date,value,unit；日期 YYYY-MM-DD，数值为有限数字，整批校验失败不入库。</p>
      <div class="row"><input type="file" id="csv-file" accept=".csv"><button class="primary" data-import>导入 CSV</button></div>
      <p class="caption">示例：Wind,螺纹钢库存,2026-11-16,100,万吨（仅格式示例）</p></div>
    <div class="panel"><h3>已入库指标（${indicators.length}）</h3>
      <div class="tablewrap"><table><thead><tr><th>来源</th><th>指标</th><th>单位</th><th>最新日期</th><th>数据点</th></tr></thead>
      <tbody>${indicators.map(x => `<tr><td>${esc(x.source)}</td><td>${esc(x.indicator)}</td><td>${esc(x.unit)}</td><td>${esc(x.latest)}</td><td>${x.points}</td></tr>`).join('') || '<tr><td colspan="5" class="empty">暂无指标</td></tr>'}</tbody></table></div></div>
    <div class="panel"><h3>最近入库记录（最多 500 条）</h3>
      <div class="tablewrap"><table><thead><tr><th>来源</th><th>指标</th><th>日期</th><th>数值</th><th>单位</th><th>导入人</th></tr></thead>
      <tbody>${S().data.map(x => `<tr><td>${esc(x.source)}</td><td>${esc(x.indicator)}</td><td>${esc(x.date)}</td><td>${esc(x.value)}</td><td>${esc(x.unit)}</td><td>${esc(x.uploaded_by || '')}</td></tr>`).join('') || '<tr><td colspan="6" class="empty">暂无数据</td></tr>'}</tbody></table></div></div></div>`;
  c.querySelector('[data-import]').onclick = () => run(async () => {
    const file = document.getElementById('csv-file').files[0];
    if (!file) throw new Error('请选择 CSV 文件');
    const result = await api('import', { csv: await file.text() });
    await refresh();
    render(document.getElementById('content'));
    toast('已导入 ' + result.count + ' 条数据');
  });
}
