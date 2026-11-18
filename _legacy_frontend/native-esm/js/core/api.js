/* 统一请求层：同源 Cookie 会话，非 2xx 一律抛出可读错误。 */
export const store = { data: null };

export async function api(path, data) {
  const init = { method: data === undefined ? 'GET' : 'POST', credentials: 'same-origin' };
  if (data !== undefined) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(data);
  }
  const res = await fetch('/api/' + path, init);
  const text = await res.text();
  let body = {};
  if (text) {
    try { body = JSON.parse(text); } catch { body = { error: '服务返回了非 JSON 响应' }; }
  }
  if (!res.ok) throw new Error(body.error || '请求失败（' + res.status + '）');
  return body;
}

export async function refresh() {
  store.data = await api('state');
  return store.data;
}

export function S() {
  return store.data || {};
}

export function can(menuKey) {
  const menus = S().user?.menus || [];
  return menus.includes('*') || menus.includes(menuKey);
}

export function isAdmin() {
  return S().user?.role === 'admin';
}
