/* 侧边菜单：结构与《研枢系统用户操作手册》一致，未实现的模块置灰并标注「未接入」。
 * 图标统一用 16×16 线稿 SVG（stroke 取 currentColor），避免各字体字形粗细、基线不一致。 */

export const ICONS = {
  grid: '<rect x="2.5" y="2.5" width="4.6" height="4.6" rx="1"/><rect x="8.9" y="2.5" width="4.6" height="4.6" rx="1"/><rect x="2.5" y="8.9" width="4.6" height="4.6" rx="1"/><rect x="8.9" y="8.9" width="4.6" height="4.6" rx="1"/>',
  layers: '<path d="M8 2.4 13.4 5.4 8 8.4 2.6 5.4Z"/><path d="M2.6 8.4 8 11.4 13.4 8.4"/><path d="M2.6 11.2 8 14.2 13.4 11.2"/>',
  doc: '<path d="M4.2 2.5h4.6l3 3v8H4.2Z"/><path d="M8.8 2.5v3h3"/><path d="M6.2 8.8h3.6M6.2 11.2h3.6"/>',
  slide: '<rect x="2.4" y="3.2" width="11.2" height="7.6" rx="1"/><path d="M8 10.8v3M6.2 13.8h3.6"/><path d="M7.2 5.8 9.6 7l-2.4 1.2Z" fill="currentColor" stroke="none"/>',
  flow: '<rect x="2.4" y="2.4" width="5.2" height="4" rx="1"/><rect x="8.4" y="9.6" width="5.2" height="4" rx="1"/><path d="M5 6.4v3.2a1.6 1.6 0 0 0 1.6 1.6h1.8"/>',
  database: '<ellipse cx="8" cy="4.2" rx="5" ry="1.9"/><path d="M3 4.2v7.6c0 1.05 2.24 1.9 5 1.9s5-.85 5-1.9V4.2"/><path d="M3 8c0 1.05 2.24 1.9 5 1.9s5-.85 5-1.9"/>',
  ruler: '<rect x="2.4" y="5.2" width="11.2" height="5.6" rx="1"/><path d="M5 5.2v2.2M7.6 5.2v3.2M10.2 5.2v2.2M12.8 5.2v3.2"/>',
  sparkle: '<path d="M8 2.6 9.5 6.5 13.4 8 9.5 9.5 8 13.4 6.5 9.5 2.6 8 6.5 6.5Z"/><path d="M12.4 2.4v1.6M13.2 3.2h-1.6"/>',
  trend: '<path d="M2.4 11.6 6 7.6l2.5 2.5 5-5.7"/><path d="M10.2 4.4h3.4v3.4"/>',
  target: '<circle cx="8" cy="8" r="5.6"/><circle cx="8" cy="8" r="2.1"/>',
  image: '<rect x="2.4" y="3.4" width="11.2" height="9.2" rx="1"/><circle cx="6" cy="6.9" r="1.2"/><path d="M2.8 11.6 6.4 8.4l2.1 1.9 2.4-2.2 2.3 2.1"/>',
  user: '<circle cx="8" cy="5.6" r="2.5"/><path d="M3.6 13.4c0-2.2 2-3.5 4.4-3.5s4.4 1.3 4.4 3.5"/>',
  table: '<rect x="2.4" y="3" width="11.2" height="10" rx="1"/><path d="M2.4 6.4h11.2M2.4 9.9h11.2M6.4 3v10"/>',
  network: '<circle cx="8" cy="3.6" r="1.8"/><circle cx="3.6" cy="12.4" r="1.8"/><circle cx="12.4" cy="12.4" r="1.8"/><path d="M8 5.4 4.5 10.8M8 5.4l3.5 5.4M5.4 12.4h5.2"/>',
  scan: '<path d="M2.6 6V4.2A1.6 1.6 0 0 1 4.2 2.6H6M10 2.6h1.8a1.6 1.6 0 0 1 1.6 1.6V6M13.4 10v1.8a1.6 1.6 0 0 1-1.6 1.6H10M6 13.4H4.2a1.6 1.6 0 0 1-1.6-1.6V10"/><path d="M5.2 8h5.6"/>',
  sigma: '<path d="M12 3.2H5l3.9 4.8L5 12.8h7"/>',
  flask: '<path d="M6.6 2.6h2.8v2.8l3 6.4a1.5 1.5 0 0 1-1.35 2.2H5a1.5 1.5 0 0 1-1.35-2.2l2.95-6.4Z"/><path d="M5.2 10.2h5.6"/>',
  box: '<rect x="2.4" y="6.2" width="11.2" height="7.2" rx="1"/><path d="M6.2 6.2V4.8a1.6 1.6 0 0 1 1.6-1.6h.4a1.6 1.6 0 0 1 1.6 1.6v1.4"/>',
  report: '<rect x="2.4" y="2.4" width="11.2" height="11.2" rx="1"/><path d="M5.6 10.8V8.4M8 10.8V6M10.4 10.8V9"/>',
  gear: '<circle cx="8" cy="8" r="2.2"/><path d="M8 2.2v1.7M8 12.1v1.7M2.2 8h1.7M12.1 8h1.7M3.9 3.9l1.2 1.2M10.9 10.9l1.2 1.2M12.1 3.9l-1.2 1.2M5.1 10.9l-1.2 1.2"/>',
  book: '<path d="M2.6 3.4h4a1.4 1.4 0 0 1 1.4 1.4v8.4a1.8 1.8 0 0 0-1.4-1.1H2.6Z"/><path d="M13.4 3.4h-4A1.4 1.4 0 0 0 8 4.8v8.4a1.8 1.8 0 0 1 1.4-1.1h4Z"/>',
  chart: '<path d="M2.6 13.4h10.8"/><rect x="4" y="8.4" width="2.2" height="4" rx=".6"/><rect x="7.4" y="5.6" width="2.2" height="6.8" rx=".6"/><rect x="10.8" y="7.2" width="2.2" height="5.2" rx=".6"/>',
};

export function iconSVG(key) {
  const body = ICONS[key];
  if (!body) return '';
  return `<svg class="menu-svg" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}

export const MENU = [
  { label: 'BI看板', icon: 'grid' },
  { label: '投研资源库', icon: 'layers' },
  { label: '研报管理', icon: 'doc', children: [
    { label: '研报中心', target: '研报中心' },
    { label: '分类列表', target: '分类配置', admin: true },
    { label: '作者管理', target: '作者管理', admin: true },
    { label: '品种管理', target: '品种管理', admin: true },
    { label: '云盘', target: '云盘' },
    { label: '文档管理库', target: '文档管理库' },
    { label: '素材库', target: '素材库' },
  ] },
  { label: '智能PPT', icon: 'slide' },
  { label: '审批管理', icon: 'flow', children: [{ label: '审批列表', target: '审核中心' }] },
  { label: '数据源', icon: 'database', children: [{ label: '手工数据录入', target: '数据中心', note: '支持 CSV 导入与数据记录查看' }] },
  { label: '指标库', icon: 'ruler' },
  { label: 'AI预测模型', icon: 'sparkle' },
  { label: '量化策略', icon: 'trend', children: [{ label: '信号生成' }, { label: '策略回测' }, { label: '因子库' }] },
  { label: '预测指标', icon: 'target' },
  { label: '图库', icon: 'image' },
  { label: '我的投研', icon: 'user', children: [{ label: '图库框架' }, { label: '我的图库' }, { label: '公共图库' }] },
  { label: '表格', icon: 'table', children: [{ label: '共享表格' }, { label: '自定义分析' }, { label: '时间序列表格' }, { label: '混合表格' }, { label: '平衡表' }] },
  { label: '逻辑图', icon: 'network' },
  { label: '语义分析', icon: 'scan', children: [{ label: 'AI纪要' }, { label: '文档管理' }, { label: '标签管理' }, { label: '文档对比' }, { label: '语音识别' }] },
  { label: '统计分析', icon: 'sigma', children: [{ label: '相关性分析' }, { label: '拟合方程曲线' }, { label: '统计特征' }, { label: '跨品种分析' }, { label: '区间分析' }, { label: 'STL趋势分解' }, { label: '残差分析' }] },
  { label: '供应分析', icon: 'flask', children: [{ label: '装置检修' }] },
  { label: '工具箱', icon: 'box', children: [{ label: '商品价格曲线' }, { label: '持仓分析' }, { label: '联储观察' }, { label: '预警管理' }, { label: 'AI问答' }] },
  { label: '数据报表管理', icon: 'report', children: [{ label: '钢联化工统计表' }, { label: '同花顺数据统计表' }, { label: 'Wind数据统计表' }, { label: '数据源巡检监控' }] },
  { label: '系统设置', icon: 'gear', admin: true, children: [
    { label: '部门管理', target: '部门管理', admin: true },
    { label: '角色管理', target: '角色管理', admin: true },
    { label: '审批流配置', target: '审批流配置', admin: true },
    { label: '基本配置', target: '系统管理', admin: true },
  ] },
];

export function breadcrumb(target) {
  for (const item of MENU) {
    const child = item.children?.find(x => x.target === target);
    if (child) return item.label + ' / ' + child.label;
    if (item.target === target) return item.label;
  }
  return target;
}
