/* 实时变更：后端只推「数据变了」的信号，这里去抖后重新拉一次 /api/state。
   所有依赖全量快照的页面因此都能自动跟上，不必各自实现刷新。 */
import { refresh } from './session';

const DEBOUNCE = 400;   // 合并短时间内的连续写操作，避免一次保存触发多次全量拉取
const MAX_RETRY = 8;    // 连续重连失败超过这个次数就停下，避免服务不可用时无限空转

let source = null;
let timer = 0;
let baseline = -1;
let pending = false;
let holds = 0;
let failures = 0;
const expireHandlers = new Set();

function notifyExpire() {
  expireHandlers.forEach(handler => {
    try {
      handler();
    } catch {
      /* 单个回调出错不该影响其它订阅者 */
    }
  });
}

function flush() {
  timer = 0;
  /* 编辑页有未保存内容时不刷新：全量快照会重建草稿，把用户正在输入的正文冲掉 */
  if (holds > 0) {
    pending = true;
    return;
  }
  if (document.visibilityState === 'hidden') {
    pending = true;
    return;
  }
  pending = false;
  refresh().catch(error => {
    if (error?.status === 401) {
      stopLive();
      notifyExpire();
    }
  });
}

function schedule() {
  if (timer) return;
  timer = setTimeout(flush, DEBOUNCE);
}

/* 会话在服务端已失效（或服务长时间不可用）时的回调，用于回登录页 */
export function onLiveExpire(handler) {
  expireHandlers.add(handler);
  return () => expireHandlers.delete(handler);
}

export function startLive() {
  if (source) return;
  baseline = -1;
  failures = 0;
  source = new EventSource('/api/events');
  source.addEventListener('ready', event => {
    failures = 0;
    let revision = 0;
    try {
      revision = Number(JSON.parse(event.data).revision) || 0;
    } catch {
      revision = 0;
    }
    /* 重连后版本号变了，说明断线期间有改动，补一次刷新 */
    if (baseline >= 0 && revision !== baseline) schedule();
    baseline = revision;
  });
  source.onmessage = event => {
    let revision;
    try {
      revision = Number(JSON.parse(event.data).revision);
    } catch {
      return;
    }
    if (revision === baseline) return;
    baseline = revision;
    schedule();
  };
  source.addEventListener('expire', () => {
    stopLive();
    notifyExpire();
  });
  source.onerror = () => {
    /* 浏览器自带重连；连续失败太多次说明服务端不可用或会话已失效，不再空转 */
    failures += 1;
    if (failures > MAX_RETRY) {
      stopLive();
      notifyExpire();
    }
  };
}

export function stopLive() {
  if (source) {
    source.close();
    source = null;
  }
  if (timer) {
    clearTimeout(timer);
    timer = 0;
  }
  pending = false;
}

/* 编辑中的页面调用：有未保存改动时暂停自动刷新，保存后再放开 */
export function pauseLive() {
  holds += 1;
}

export function resumeLive() {
  if (holds > 0) holds -= 1;
  if (holds === 0 && pending) schedule();
}

/* 从后台切回来时补一次：后台期间的变更不能一直压着不刷 */
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && pending) schedule();
});

/* 整页跳转 / 关标签页时主动断开。浏览器销毁页面虽然也会关连接，但那是异步的：
   接连跳几个页面，几条 SSE 会短时间一起挂在连接池里，把同源 6 个名额占满，
   后续请求就只能排队等到超时。 */
window.addEventListener('pagehide', stopLive);
