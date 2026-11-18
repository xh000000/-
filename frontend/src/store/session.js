/* 会话与全量业务状态。后端 /api/state 一次返回全部可见数据，前端只做视图层筛选。 */
import { computed, reactive } from 'vue';
import { api } from '../api';

export const session = reactive({
  ready: false,
  setup: false,
  data: null,
  error: '',
});

export const user = computed(() => session.data?.user || {});
export const reports = computed(() => session.data?.reports || []);
export const categories = computed(() => session.data?.categories || []);
export const categoryTree = computed(() => session.data?.category_tree || []);
export const authors = computed(() => session.data?.authors || []);
export const commodities = computed(() => session.data?.commodities || []);
export const members = computed(() => session.data?.members || []);
export const library = computed(() => session.data?.library || []);
export const indicators = computed(() => session.data?.indicators || []);
export const dataRows = computed(() => session.data?.data || []);
export const users = computed(() => session.data?.users || []);
export const roles = computed(() => session.data?.roles || []);
export const departments = computed(() => session.data?.departments || []);
export const flows = computed(() => session.data?.flows || []);

export const isAdmin = computed(() => user.value.role === 'admin');

export function can(menuKey) {
  const menus = user.value.menus || [];
  return menus.includes('*') || menus.includes(menuKey);
}

export async function refresh() {
  session.data = await api('state');
  return session.data;
}

export async function bootstrap() {
  const info = await api('bootstrap');
  session.setup = Boolean(info.setup);
  return info;
}

/* 首次进入：先判断是否需要初始化，再尝试读取业务状态。 */
export async function boot() {
  session.error = '';
  try {
    const info = await bootstrap();
    if (info.setup) {
      session.data = null;
      return;
    }
    await refresh();
  } catch (error) {
    session.data = null;
    if (error.status !== 401) session.error = error.message || '服务不可用';
  } finally {
    session.ready = true;
  }
}

export async function login(name, password, remember) {
  await api(session.setup ? 'setup' : 'login', { name, password, remember });
  await refresh();
}

export async function logout() {
  try {
    await api('logout', {});
  } finally {
    session.data = null;
  }
}

export function reportById(id) {
  return reports.value.find(item => item.id === Number(id)) || null;
}

export const memberName = id => members.value.find(item => item.id === id)?.name || '#' + id;
