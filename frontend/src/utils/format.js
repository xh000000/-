/* 展示口径集中在这里：状态码在服务端，中文措辞与《研枢系统用户操作手册》保持一致。 */

export const ROLE_NAMES = {
  admin: '管理员',
  researcher: '研究员',
  reviewer: '研究复核',
  compliance: '合规审核',
  publisher: '发布专员',
};

export const STATUS_TEXT = {
  草稿: '待提交',
  研究复核: '待审批',
  合规审核: '待审批',
  待发布: '已通过',
  已发布: '已发布',
  已退回: '已驳回',
};

export const STATUS_ORDER = { 已发布: 0, 待发布: 1, 研究复核: 2, 合规审核: 2, 已退回: 3, 草稿: 4 };

export const statusText = report => STATUS_TEXT[report?.status] || report?.status || '';

export const TAG_TYPE = {
  已发布: 'success',
  待发布: 'primary',
  草稿: 'info',
  已退回: 'danger',
  研究复核: 'warning',
  合规审核: 'warning',
};

export const MODE_NAMES = { any: '或签', all: '会签', sequential: '依次审批' };

export const MENU_KEYS = [
  '工作台', '数据中心', '研报中心', '审核中心', '云盘', '文档管理库', '素材库',
  '分类配置', '作者管理', '品种管理', '审批流配置', '角色管理', '部门管理', '系统管理',
];

export const escapeHtml = value =>
  String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

export function sortReports(list) {
  return [...list].sort(
    (a, b) =>
      (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9) ||
      String(b.updated).localeCompare(String(a.updated))
  );
}

export function parseJSON(value, fallback = null) {
  if (!value) return fallback;
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

export function localTime(value) {
  if (!value) return '—';
  const date = new Date(String(value).replace(' UTC', 'Z').replace(' ', 'T'));
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(date);
}

export const today = () => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date());

export const dateOnly = value => String(value || '').slice(0, 10);

export const fileSize = bytes => {
  const size = Number(bytes || 0);
  if (size < 1024) return size + ' B';
  if (size < 1024 * 1024) return (size / 1024).toFixed(1) + ' KB';
  return (size / 1024 / 1024).toFixed(1) + ' MB';
};

export const makeId = () =>
  window.crypto?.randomUUID ? window.crypto.randomUUID() : 'b-' + Date.now() + '-' + Math.random().toString(16).slice(2);
