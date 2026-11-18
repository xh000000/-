/* 通用 UI 原语与状态口径。状态码在服务端，展示文案在这里统一成手册口径。 */
export const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export const ROLE_NAMES = { admin: '管理员', researcher: '研究员', reviewer: '研究复核', compliance: '合规审核', publisher: '发布专员' };

export const STATUS_TEXT = { '草稿': '待提交', '研究复核': '待审批', '合规审核': '待审批', '待发布': '已通过', '已发布': '已发布', '已退回': '已驳回' };
export const STATUS_ORDER = { '已发布': 0, '待发布': 1, '研究复核': 2, '合规审核': 2, '已退回': 3, '草稿': 4 };

export const statusText = r => STATUS_TEXT[r.status] || r.status;

export function toast(message) {
  const box = document.getElementById('notice');
  if (!box) return;
  box.textContent = message;
  box.style.display = 'block';
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { box.style.display = 'none'; }, 5000);
}

export async function run(fn) {
  try {
    await fn();
  } catch (error) {
    toast(error.message || String(error));
  }
}

export function modal(html, options = {}) {
  const dialog = document.getElementById('modal');
  dialog.className = 'app-dialog' + (options.wide ? ' dialog-wide' : '') + (options.plain ? ' dialog-plain' : '');
  dialog.innerHTML = (options.plain ? '' : '<div class="dialog-head"><b>' + esc(options.title || '操作') + '</b><button type="button" data-close aria-label="关闭">×</button></div>') + html;
  dialog.querySelectorAll('[data-close]').forEach(button => button.onclick = () => dialog.close());
  if (!dialog.open) dialog.showModal();
  // 打开后把焦点放到第一个表单控件，避免浏览器把焦点留在关闭按钮上（会显示一圈焦点框）。
  const first = dialog.querySelector('input:not([type=hidden]), select, textarea');
  if (first) first.focus();
  else dialog.focus();
  return dialog;
}

export function closeModal() {
  const dialog = document.getElementById('modal');
  if (dialog?.open) dialog.close();
}

export function confirmAction(title, message, onOk, okText = '确认') {
  modal('<div class="dialog-body"><p>' + esc(message) + '</p><form id="confirm-form" class="dialog-actions"><button type="button" data-close>取消</button><button class="primary">' + esc(okText) + '</button></form></div>', { title });
  document.getElementById('confirm-form').onsubmit = event => {
    event.preventDefault();
    closeModal();
    onOk();
  };
}

export const formObject = form => Object.fromEntries(new FormData(form));
export const localTime = value => {
  if (!value) return '—';
  const date = new Date(String(value).replace(' UTC', 'Z').replace(' ', 'T'));
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date);
};
export const today = () => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date());

export function empty(text) {
  return '<div class="empty">' + esc(text) + '</div>';
}

export function badgeColor(status) {
  if (status === '已发布') return 'green';
  if (status === '已退回') return 'red';
  if (status === '待发布') return 'blue';
  if (status === '草稿') return 'gray';
  return 'amber';
}
