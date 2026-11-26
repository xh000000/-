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
          :default-openeds="opened"
          background-color="#304156"
          text-color="#bfcbd9"
          active-text-color="#409EFF"
          router
        >
          <template v-for="group in visibleMenu" :key="group.label">
            <el-sub-menu v-if="group.children" :index="'g:' + group.label" :disabled="group.disabled">
              <template #title>
                <el-icon><component :is="group.icon" /></el-icon>
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
              <el-icon><component :is="group.icon" /></el-icon>
              <span>{{ group.label }}</span>
            </el-menu-item>
          </template>
        </el-menu>
      </nav>
      <div class="app-aside-foot">
        <b>{{ user.name }} · {{ roleName }}</b>
        <span class="foot-note">私有化部署 · 数据留痕</span>
      </div>
    </el-aside>

    <el-container class="app-body">
      <TabsBar />
      <el-header class="app-header" height="56px">
        <div class="crumb">
          <template v-for="(part, index) in crumbs" :key="part">
            <span v-if="index" class="sep">/</span>
            <b v-if="index === crumbs.length - 1">{{ part }}</b>
            <span v-else>{{ part }}</span>
          </template>
        </div>
        <div class="tools">
          <AccountMenu @password="passwordVisible = true" @logout="onLogout" />
        </div>
      </el-header>
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
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { MENU, breadcrumb, filterMenu } from '../utils/menu';
import { ROLE_NAMES } from '../utils/format';
import { isAdmin, logout, user, session } from '../store/session';
import ChangePasswordDialog from '../components/ChangePasswordDialog.vue';
import AccountMenu from '../components/AccountMenu.vue';
import TabsBar from '../components/TabsBar.vue';

const route = useRoute();
const router = useRouter();
const passwordVisible = ref(false);

const roleName = computed(() => ROLE_NAMES[user.value.role] || user.value.role || '');
const crumbs = computed(() => breadcrumb(route.path));

/* 全局显示开关叠加账号权限；系统设置及其全部子菜单仅管理员可见。 */
const visibleMenu = computed(() => filterMenu(MENU, user.value, session.data?.menu_visibility || {}));

/* 当前页所属分组默认展开，其余按手册的常用入口各展开一个。 */
const opened = computed(() => {
  const labels = ['g:研报管理'];
  if (isAdmin.value) labels.push('g:系统设置', 'g:审批管理');
  const current = visibleMenu.value.find(group => group.children?.some(child => child.path === route.path));
  if (current && !labels.includes('g:' + current.label)) labels.push('g:' + current.label);
  return labels;
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
