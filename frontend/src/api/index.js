/* 统一请求层：同源 Cookie 会话；非 2xx 一律抛出可读错误，由调用方决定提示方式。 */
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

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
    try {
      body = JSON.parse(text);
    } catch {
      body = { error: '服务返回了非 JSON 响应' };
    }
  }
  if (!res.ok) throw new ApiError(body.error || `请求失败（${res.status}）`, res.status);
  return body;
}

/* DELETE 请求（Agent 线程删除等）。 */
export async function del(path) {
  const res = await fetch('/api/' + path, { method: 'DELETE', credentials: 'same-origin' });
  const text = await res.text();
  let body = {};
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { error: '服务返回了非 JSON 响应' };
    }
  }
  if (!res.ok) throw new ApiError(body.error || `请求失败（${res.status}）`, res.status);
  return body;
}

/* 二进制下载（打包 zip、原始文件、打印页）走浏览器直连，不经过 fetch。 */
export const fileUrl = id => `/api/library/file/${id}`;
export const downloadUrl = id => `/api/library/file/${id}?download=1`;
export const printUrl = id => `/api/report-print/${id}`;
