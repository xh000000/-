<template>
  <el-popover v-model:visible="visible" placement="bottom-end" :width="320" trigger="click">
    <template #reference>
      <button type="button" class="user-chip account-trigger" aria-label="我的账号" :aria-expanded="visible">
        <i>{{ initial }}</i><span>{{ user.name }}</span><em>{{ roleName }}</em><span aria-hidden="true">⌄</span>
      </button>
    </template>
    <section class="account-panel" aria-label="账号信息">
      <h3>我的账号</h3>
      <dl>
        <div><dt>姓名</dt><dd>{{ user.name || '—' }}</dd></div>
        <div><dt>角色</dt><dd>{{ roleName }}</dd></div>
        <div><dt>部门</dt><dd>{{ user.dept_name || '—' }}</dd></div>
        <div><dt>手机</dt><dd>{{ user.phone || '—' }}</dd></div>
        <div><dt>职务</dt><dd>{{ user.title || '—' }}</dd></div>
      </dl>
      <div class="account-actions">
        <el-button type="primary" plain @click="act('password')">修改密码</el-button>
        <el-button @click="act('logout')">退出登录</el-button>
      </div>
    </section>
  </el-popover>
</template>
<script setup>
import { computed, ref } from 'vue';
import { user } from '../store/session';
import { ROLE_NAMES } from '../utils/format';
const emit = defineEmits(['password', 'logout']);
const visible = ref(false);
const roleName = computed(() => ROLE_NAMES[user.value.role] || user.value.role || '—');
const initial = computed(() => String(user.value.name || '研').slice(0, 1));
function act(action) { visible.value = false; emit(action); }
</script>
<style scoped>
.account-trigger { border: 0; background: transparent; font: inherit; cursor: pointer; border-radius: 6px; padding: 5px 8px; }
.account-trigger:hover { background: var(--el-fill-color-light); }
.account-trigger:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 2px; }
.account-panel { padding: 6px; }
.account-panel h3 { margin: 0 0 16px; font-size: 15px; }
.account-panel dl { margin: 0; }
.account-panel dl > div { display: flex; gap: 16px; margin-bottom: 12px; font-size: 13px; }
.account-panel dt { width: 42px; flex-shrink: 0; color: var(--el-text-color-secondary); }
.account-panel dd { margin: 0; color: var(--el-text-color-primary); overflow-wrap: anywhere; }
.account-actions { display: flex; border-top: 1px solid var(--el-border-color-lighter); padding-top: 14px; margin-top: 16px; }
</style>
