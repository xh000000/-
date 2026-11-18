import { createRouter, createWebHistory } from 'vue-router';
import { boot, session } from '../store/session';

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
    meta: { public: true, title: '登录' },
  },
  {
    path: '/',
    component: () => import('../layout/AppLayout.vue'),
    children: [
      { path: '', name: 'dashboard', component: () => import('../views/DashboardView.vue'), meta: { title: '工作台' } },
      { path: 'reports', name: 'reports', component: () => import('../views/ReportListView.vue'), meta: { title: '研报中心' } },
      { path: 'approval', name: 'approval', component: () => import('../views/ApprovalView.vue'), meta: { title: '审核中心' } },
      {
        path: 'library/:area(cloud|docs|materials)',
        name: 'library',
        component: () => import('../views/LibraryView.vue'),
        meta: { title: '资料库' },
      },
      { path: 'data', name: 'data', component: () => import('../views/DataView.vue'), meta: { title: '手工数据录入' } },
      { path: 'data/indicators', name: 'indicators', component: () => import('../views/IndicatorView.vue'), meta: { title: '指标查询' } },
      { path: 'config/categories', name: 'categories', component: () => import('../views/CategoriesView.vue'), meta: { title: '研报分类树' } },
      { path: 'config/authors', name: 'authors', component: () => import('../views/AuthorsView.vue'), meta: { title: '署名作者' } },
      { path: 'config/commodities', name: 'commodities', component: () => import('../views/CommoditiesView.vue'), meta: { title: '研究品种' } },
      { path: 'config/flows', name: 'flows', component: () => import('../views/FlowsView.vue'), meta: { title: '审批流配置' } },
      { path: 'system/departments', name: 'departments', component: () => import('../views/DepartmentsView.vue'), meta: { title: '部门管理' } },
      { path: 'system/roles', name: 'roles', component: () => import('../views/RolesView.vue'), meta: { title: '角色管理' } },
      { path: 'system/settings', name: 'settings', component: () => import('../views/SettingsView.vue'), meta: { title: '基本配置' } },
    ],
  },
  {
    path: '/reports/:id',
    name: 'editor',
    component: () => import('../views/ReportEditorView.vue'),
    meta: { title: '研报编辑', fullscreen: true },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
});

router.beforeEach(async to => {
  if (!session.ready) await boot();
  if (to.meta.public) {
    return session.data ? { name: 'dashboard' } : true;
  }
  if (!session.data) return { name: 'login' };
  return true;
});

router.afterEach(to => {
  document.title = (to.meta.title ? to.meta.title + ' · ' : '') + '研枢 · 期货研究管理平台';
});

export default router;
