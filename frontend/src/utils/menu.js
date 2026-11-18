/* 侧边菜单：分组结构与《研枢系统用户操作手册》一致；未接入模块保留位置并置灰，不提供空壳页面。 */
import {
  Aim, Box, Collection, Connection, DataBoard, DataLine, Document, Finished,
  Grid, MagicStick, Monitor, Odometer, Picture, PieChart, Setting, Share,
  Tickets, Tools, TrendCharts, User, View,
} from '@element-plus/icons-vue';

export const MENU = [
  { label: 'BI看板', icon: DataBoard, disabled: true },
  { label: '投研资源库', icon: Collection, disabled: true },
  {
    label: '研报管理', icon: Document, children: [
      { label: '研报中心', path: '/reports' },
      { label: '分类列表', path: '/config/categories', admin: true },
      { label: '作者管理', path: '/config/authors', admin: true },
      { label: '品种管理', path: '/config/commodities', admin: true },
      { label: '云盘', path: '/library/cloud' },
      { label: '文档管理库', path: '/library/docs' },
      { label: '素材库', path: '/library/materials' },
    ],
  },
  { label: '智能PPT', icon: Monitor, disabled: true },
  { label: '审批管理', icon: Finished, children: [{ label: '审批列表', path: '/approval' }] },
  {
    label: '数据源', icon: DataLine, children: [
      { label: '数据录入', path: '/data' },
      { label: '指标查询', path: '/data/indicators' },
    ],
  },
  { label: '指标库', icon: Odometer, disabled: true },
  { label: 'AI预测模型', icon: MagicStick, disabled: true },
  {
    label: '量化策略', icon: TrendCharts, disabled: true, children: [
      { label: '信号生成' }, { label: '策略回测' }, { label: '因子库' },
    ],
  },
  { label: '预测指标', icon: Aim, disabled: true },
  { label: '图库', icon: Picture, disabled: true },
  {
    label: '我的投研', icon: User, disabled: true, children: [
      { label: '图库框架' }, { label: '我的图库' }, { label: '公共图库' },
    ],
  },
  {
    label: '表格', icon: Grid, disabled: true, children: [
      { label: '共享表格' }, { label: '自定义分析' }, { label: '时间序列表格' },
      { label: '混合表格' }, { label: '平衡表' },
    ],
  },
  { label: '逻辑图', icon: Connection, disabled: true },
  {
    label: '语义分析', icon: View, disabled: true, children: [
      { label: 'AI纪要' }, { label: '文档管理' }, { label: '标签管理' },
      { label: '文档对比' }, { label: '语音识别' },
    ],
  },
  {
    label: '统计分析', icon: PieChart, disabled: true, children: [
      { label: '相关性分析' }, { label: '拟合方程曲线' }, { label: '统计特征' },
      { label: '跨品种分析' }, { label: '区间分析' }, { label: 'STL趋势分解' }, { label: '残差分析' },
    ],
  },
  { label: '供应分析', icon: Box, disabled: true, children: [{ label: '装置检修' }] },
  {
    label: '工具箱', icon: Tools, disabled: true, children: [
      { label: '商品价格曲线' }, { label: '持仓分析' }, { label: '联储观察' },
      { label: '预警管理' }, { label: 'AI问答' },
    ],
  },
  {
    label: '数据报表管理', icon: Tickets, disabled: true, children: [
      { label: '钢联化工统计表' }, { label: '同花顺数据统计表' },
      { label: 'Wind数据统计表' }, { label: '数据源巡检监控' },
    ],
  },
  {
    label: '系统设置', icon: Setting, admin: true, children: [
      { label: '部门管理', path: '/system/departments', admin: true },
      { label: '账号管理', path: '/system/users', admin: true },
      { label: '角色管理', path: '/system/roles', admin: true },
      { label: '审批流设置', path: '/config/flows', admin: true },
      { label: '外部模型', path: '/system/models', admin: true },
      { label: '菜单管理', path: '/system/menus', admin: true },
    ],
  },
];

export function breadcrumb(path) {
  if (path === '/') return ['工作台'];
  for (const group of MENU) {
    const child = group.children?.find(item => item.path === path);
    if (child) return [group.label, child.label];
    if (group.path === path) return [group.label];
  }
  return ['研枢'];
}

/* 顶部标题用的页面名（与菜单末级一致）。 */
export function pageTitle(path) {
  const parts = breadcrumb(path);
  return parts[parts.length - 1];
}

/* Stable identifiers use route paths where available; placeholder modules use their hierarchy. */
export function menuId(item, parent = null) {
  return item.path || (parent ? `item:${parent.label}:${item.label}` : `group:${item.label}`);
}

export const PROTECTED_MENU_IDS = ['group:系统设置', '/system/menus'];
const PERMISSIONS = {
  '/reports': '研报中心', '/approval': '审核中心',
  '/data': '数据中心', '/data/indicators': '数据中心',
  '/library/cloud': '云盘', '/library/docs': '文档管理库', '/library/materials': '素材库',
  '/config/categories': '分类配置', '/config/authors': '作者管理',
  '/config/commodities': '品种管理', '/config/flows': '审批流配置',
  '/system/departments': '部门管理', '/system/users': '系统管理', '/system/roles': '角色管理',
  '/system/models': '系统管理', '/system/settings': '系统管理', '/system/menus': '系统管理',
};

export function filterMenu(items, account, visibility = {}) {
  const admin = account.role === 'admin';
  const permissions = account.menus || [];
  const shown = (item, parent) => {
    const id = menuId(item, parent);
    if (item.admin && !admin) return false;
    if (!PROTECTED_MENU_IDS.includes(id) && visibility[id] === false) return false;
    const permission = PERMISSIONS[item.path];
    return admin || !permission || permissions.includes('*') || permissions.includes(permission);
  };
  return items.filter(item => shown(item)).map(item => item.children
    ? { ...item, children: item.children.filter(child => shown(child, item)) } : item
  ).filter(item => !item.children || item.children.length);
}
