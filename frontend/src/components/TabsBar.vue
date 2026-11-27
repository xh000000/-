<template>
  <div class="tabs-bar">
    <div class="tabs-main">
      <button v-show="overflow.left" class="scroll-btn is-left" type="button" title="向左滚动" @click="scrollBy(-240)">
        <el-icon><ArrowLeft /></el-icon>
      </button>
      <div ref="trackRef" class="tabs-track" @wheel="onWheel" @scroll="updateOverflow">
        <div
          v-for="tab in tabs"
          :key="tab.path"
          class="tab"
          :class="{ 'is-active': tab.path === route.path }"
          :title="tab.title"
          @click="go(tab)"
          @contextmenu="openMenu($event, tab)"
        >
          <span class="label">{{ tab.title }}</span>
          <el-icon v-if="tab.closable" class="close" @click.stop="closeTab(tab)"><Close /></el-icon>
        </div>
      </div>
      <button v-show="overflow.right" class="scroll-btn is-right" type="button" title="向右滚动" @click="scrollBy(240)">
        <el-icon><ArrowRight /></el-icon>
      </button>
    </div>
    <div v-if="$slots.tools" class="tabs-tools">
      <slot name="tools" />
    </div>
  </div>

  <Teleport to="body">
    <div v-if="menu.visible" class="tab-menu" :style="{ left: menu.x + 'px', top: menu.y + 'px' }">
      <button type="button" :disabled="!menu.tab?.closable" @click="menuAction('close')">关闭当前</button>
      <button type="button" @click="menuAction('others')">关闭其他</button>
      <button type="button" @click="menuAction('all')">关闭全部</button>
    </div>
  </Teleport>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Close, ArrowLeft, ArrowRight } from '@element-plus/icons-vue';
import { pageTitle } from '../utils/menu';
import { user } from '../store/session';

/* 页签栏：记录访问过的页面。工作台常驻不可关，其余可关闭；
   页签多了不会折叠换行，而是横向滚动（溢出时两端出现箭头，当前页签自动滚到可见）。 */
const STORAGE_KEY = 'app.tabs.v1';
const route = useRoute();
const router = useRouter();
const tabs = ref([]);
const trackRef = ref(null);
const menu = reactive({ visible: false, x: 0, y: 0, tab: null });
const overflow = reactive({ left: false, right: false });

/* 页签名优先取菜单名（资料库下三个页面路由同名，靠菜单名区分） */
function titleOf(path, meta) {
  const name = pageTitle(path);
  return name && name !== '研枢' ? name : (meta?.title || path);
}

function sync() {
  if (route.meta?.fullscreen || !route.meta?.title) return;
  if (tabs.value.some(tab => tab.path === route.path)) return;
  tabs.value.push({ path: route.path, title: titleOf(route.path, route.meta), closable: route.path !== '/' });
}

function go(tab) {
  menu.visible = false;
  if (tab.path !== route.path) router.push(tab.path);
}

function closeTab(tab) {
  if (!tab.closable) return;
  const index = tabs.value.findIndex(item => item.path === tab.path);
  if (index < 0) return;
  tabs.value.splice(index, 1);
  if (route.path === tab.path) {
    const next = tabs.value[index] || tabs.value[index - 1];
    router.push(next ? next.path : '/');
  }
}

function scrollActive() {
  const track = trackRef.value;
  const tab = track?.querySelector('.tab.is-active');
  if (!track || !tab) return;
  const left = tab.offsetLeft;
  const right = left + tab.offsetWidth;
  if (left < track.scrollLeft) track.scrollLeft = Math.max(0, left - 26);
  else if (right > track.scrollLeft + track.clientWidth) track.scrollLeft = right - track.clientWidth + 26;
  updateOverflow();
}

/* 溢出方向：决定左右箭头显不显示 */
function updateOverflow() {
  const track = trackRef.value;
  if (!track) return;
  overflow.left = track.scrollLeft > 2;
  overflow.right = track.scrollLeft + track.clientWidth < track.scrollWidth - 2;
}

function scrollBy(delta) {
  trackRef.value?.scrollBy({ left: delta, behavior: 'smooth' });
}

function onWheel(event) {
  if (!trackRef.value || Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
  event.preventDefault();
  trackRef.value.scrollLeft += event.deltaY;
}

function openMenu(event, tab) {
  event.preventDefault();
  menu.tab = tab;
  menu.x = event.clientX;
  menu.y = Math.min(event.clientY, window.innerHeight - 120);
  menu.visible = true;
}

function hideMenu() { menu.visible = false; }

function menuAction(action) {
  const target = menu.tab;
  menu.visible = false;
  if (action === 'close' && target) {
    closeTab(target);
    return;
  }
  if (action === 'others') {
    const keep = target && target.closable ? target : tabs.value.find(tab => tab.path === route.path);
    tabs.value = tabs.value.filter(tab => !tab.closable || tab.path === keep?.path);
    if (keep && route.path !== keep.path) router.push(keep.path);
    return;
  }
  if (action === 'all') {
    tabs.value = tabs.value.filter(tab => !tab.closable);
    if (route.path !== '/') router.push('/');
  }
}

watch(route, () => {
  sync();
  nextTick(scrollActive);
});

watch(tabs, value => {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    /* 隐私模式或超额时忽略，不影响使用 */
  }
  nextTick(updateOverflow);
}, { deep: true });

onMounted(() => {
  let saved = [];
  try {
    saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]');
  } catch {
    saved = [];
  }
  const seen = new Set();
  tabs.value = (Array.isArray(saved) ? saved : []).filter(item => {
    if (!item?.path || seen.has(item.path)) return false;
    seen.add(item.path);
    const resolved = router.resolve(item.path);
    if (!resolved.matched.length || resolved.meta?.fullscreen) return false;
    if (resolved.meta?.admin && user.value.role !== 'admin') return false;
    return true;
  }).map(item => ({ path: item.path, title: item.title || titleOf(item.path), closable: item.path !== '/' }));
  sync();
  nextTick(scrollActive);
  document.addEventListener('click', hideMenu);
  window.addEventListener('resize', updateOverflow);
});

onBeforeUnmount(() => {
  document.removeEventListener('click', hideMenu);
  window.removeEventListener('resize', updateOverflow);
});
</script>

<style scoped>
.tabs-bar {
  flex: none;
  display: flex;
  align-items: stretch;
  height: var(--app-tabs-h);
  background: var(--surface);
  border-bottom: 1px solid var(--line);
}
.tabs-main {
  position: relative;
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: stretch;
}
.tabs-track {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: stretch;
  gap: 0;
  height: 100%;
  padding: 0 20px;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: none;
}
.tabs-track::-webkit-scrollbar { height: 0; }
/* 右侧工具位：账号等信息放在页签同一行，省掉一条独立工具栏 */
.tabs-tools {
  flex: none;
  display: flex;
  align-items: center;
  padding: 0 10px 0 12px;
  border-left: 1px solid var(--line-2);
}

/* 页签溢出时的左右滚动按钮，贴在两端，白底渐隐压住底下文字 */
.scroll-btn {
  position: absolute;
  top: 0;
  bottom: 0;
  z-index: 2;
  width: 22px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  color: var(--ink-3);
  background: var(--surface);
  cursor: pointer;
}
.scroll-btn .el-icon { font-size: 12px; }
.scroll-btn:hover { color: var(--accent); }
.scroll-btn.is-left { left: 0; }
.scroll-btn.is-right { right: 0; }

/* 页签＝一段文字，激活用底部一道墨蓝线标示，不额外加框 */
.tab {
  position: relative;
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 190px;
  padding: 0 12px;
  font-size: 13px;
  color: var(--ink-2);
  white-space: nowrap;
  cursor: pointer;
  user-select: none;
  transition: color 0.15s ease;
}
.tab .label { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.tab:hover { color: var(--ink-1); background: var(--el-fill-color-light); }
.tab.is-active { color: var(--ink-1); font-weight: 600; }
.tab.is-active::after {
  content: '';
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 0;
  height: 2px;
  background: var(--accent);
}
/* 图标所在的盒子固定 15px：el-icon 默认 1em，加 padding 会被全局 border-box 压扁 */
.tab .close {
  flex: none;
  width: 15px;
  height: 15px;
  font-size: 11px;
  color: var(--ink-3);
  border-radius: 2px;
  opacity: 0;
  transition: opacity 0.15s ease, background-color 0.15s ease, color 0.15s ease;
}
.tab:hover .close,
.tab.is-active .close { opacity: 1; }
.tab .close:hover { background: #f0f3f5; color: var(--up); }

.tab-menu {
  position: fixed;
  z-index: 3000;
  min-width: 116px;
  padding: 4px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--el-box-shadow-light);
}
.tab-menu button {
  display: block;
  width: 100%;
  padding: 6px 10px;
  border: 0;
  border-radius: var(--radius);
  background: none;
  font-family: inherit;
  font-size: 12.5px;
  color: var(--ink-2);
  text-align: left;
  cursor: pointer;
}
.tab-menu button:hover:not(:disabled) { background: var(--el-fill-color-light); color: var(--ink-1); }
.tab-menu button:disabled { color: var(--el-text-color-placeholder); cursor: not-allowed; }
</style>
