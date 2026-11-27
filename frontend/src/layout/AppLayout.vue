<template>
  <el-container class="app-shell">
    <el-aside class="app-aside" :width="'var(--app-aside-w)'">
      <router-link class="app-brand" to="/" title="返回工作台">
        <span class="mark">
          <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path d="M3 14.4 8 9.2l3 2.4 5.9-6.5" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" />
            <circle cx="16.9" cy="5.1" r="1.8" fill="#fff" />
            <path d="M3 16.9h14" stroke="#fff" stroke-opacity=".5" stroke-width="1.5" stroke-linecap="round" />
          </svg>
        </span>
        <span class="text">
          <b>研枢</b>
          <small>投研平台</small>
        </span>
      </router-link>
      <nav class="app-nav">
        <el-menu
          :default-active="route.path"
          :default-openeds="[]"
          background-color="#304156"
          text-color="#bfcbd9"
          active-text-color="#ffffff"
          router
        >
          <template v-for="group in visibleMenu" :key="group.label">
            <el-sub-menu v-if="group.children" :index="'g:' + group.label" :disabled="group.disabled">
              <template #title>
                <el-icon><component :is="iconOf(group.icon)" /></el-icon>
                <span>{{ group.label }}</span>
              </template>
              <el-menu-item
                v-for="child in group.children"
                :key="child.label"
                :index="child.path || 'x:' + group.label + ':' + child.label"
                :disabled="!child.path"
              >
                {{ child.label }}
              </el-menu-item>
            </el-sub-menu>
            <el-menu-item v-else :index="group.path || 'x:' + group.label" :disabled="group.disabled">
              <el-icon><component :is="iconOf(group.icon)" /></el-icon>
              <span>{{ group.label }}</span>
            </el-menu-item>
          </template>
        </el-menu>
      </nav>
      <div class="app-aside-foot">
        <b>{{ user.name }} · {{ roleName }}</b>
        <span class="foot-note">私有化部署 · 数据留痕</span>
        <span class="foot-note build-stamp">UI 构建号 1175</span>
      </div>
    </el-aside>

    <el-container class="app-body">
      <TabsBar>
        <template #tools>
          <AccountMenu @password="passwordVisible = true" @logout="onLogout" />
        </template>
      </TabsBar>
      <el-main class="app-main">
        <router-view v-slot="{ Component }">
          <component :is="Component" />
        </router-view>
      </el-main>
    </el-container>

    <ChangePasswordDialog v-model="passwordVisible" />
  </el-container>
</template>

<script setup>
import { computed, onUnmounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { iconOf } from '../utils/menu';
import { ROLE_NAMES } from '../utils/format';
import { logout, user, session } from '../store/session';
import { onLiveExpire, startLive, stopLive } from '../store/live';
import ChangePasswordDialog from '../components/ChangePasswordDialog.vue';
import AccountMenu from '../components/AccountMenu.vue';
import TabsBar from '../components/TabsBar.vue';

const route = useRoute();
const router = useRouter();
const passwordVisible = ref(false);

const roleName = computed(() => ROLE_NAMES[user.value.role] || user.value.role || '');

/* 菜单目录由后端菜单表按「显示开关 + 权限」过滤后随 /api/state 下发，这里只渲染。 */
const visibleMenu = computed(() => session.data?.menus || []);

/* 菜单分组默认收起，由用户按需点击展开。 */

/* 登录后保持一条 SSE 长连接：任何写操作都会推进服务端版本号，收到就重新拉快照，
   菜单显示、研报状态、审批节点这些「以前要刷新才变」的内容会自动跟上。 */
startLive();
const offExpire = onLiveExpire(() => {
  ElMessage.warning('登录状态已失效，请重新登录');
  router.replace({ name: 'login' });
});
onUnmounted(() => {
  offExpire();
  stopLive();
});

async function onLogout() {
  try {
    await ElMessageBox.confirm('退出后需要重新输入账号密码登录。', '退出登录', {
      confirmButtonText: '退出', cancelButtonText: '取消', type: 'warning',
    });
  } catch {
    return;
  }
  await logout();
  ElMessage.success('已退出');
  router.replace({ name: 'login' });
}
</script>
