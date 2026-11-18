/* 页面注册表：key 与侧边菜单 target 一一对应。 */
import * as dashboard from './dashboard.js';
import * as reports from './reports.js';
import * as config from './config.js';
import * as library from './library.js';
import * as system from './system.js';
import * as data from './data.js';

const libraryPage = key => ({ render: host => library.render(host, key) });

export const PAGES = {
  '工作台': dashboard,
  '数据中心': data,
  '研报中心': reports,
  '审核中心': reports,
  '云盘': libraryPage('云盘'),
  '文档管理库': libraryPage('文档管理库'),
  '素材库': libraryPage('素材库'),
  '分类配置': { render: config.renderCategories },
  '作者管理': { render: config.renderAuthors },
  '品种管理': { render: config.renderCommodities },
  '审批流配置': { render: config.renderFlows },
  '角色管理': { render: system.renderRoles },
  '部门管理': { render: system.renderDepartments },
  '系统管理': { render: system.renderSettings },
};
