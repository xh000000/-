<template>
  <div>
    <PageContainer title="菜单管理">
      <template #actions>
        <el-button :disabled="loading || saving" @click="restoreDefaults">恢复默认</el-button>
        <el-button :loading="loading" :disabled="saving" @click="load">重新加载</el-button>
        <el-button type="primary" :loading="saving" :disabled="loading || !dirty" @click="save">保存设置</el-button>
      </template>
    <div class="panel">
      <div class="panel-header"><h3>菜单目录</h3><span v-if="dirty" class="caption">有未保存的修改</span></div>
      <p class="caption menu-note">菜单目录存在数据库 menus 表；这里改显示开关后，所有账号刷新页面即按新目录展示。只影响导航显示，不改变角色权限。</p>
      <el-table v-loading="loading" :data="rows" row-key="id" default-expand-all max-height="650">
        <el-table-column label="菜单名称" min-width="200">
          <template #default="{ row }"><span>{{ row.label }}</span><el-tag v-if="row.admin_only" size="small" type="info" effect="plain" class="menu-tag">仅管理员</el-tag></template>
        </el-table-column>
        <el-table-column label="页面路径" min-width="200"><template #default="{ row }"><span class="caption">{{ row.path || (row.children ? '菜单分组' : '暂未接入') }}</span></template></el-table-column>
        <el-table-column label="显示" width="110" align="center">
          <template #default="{ row }"><el-switch :model-value="row.visible" :disabled="loading || saving || row.protected || parentHidden(row)"
            :aria-label="`${row.label}显示开关`" @update:model-value="value => setVisible(row, value)" /></template>
        </el-table-column>
        <el-table-column label="说明" min-width="200"><template #default="{ row }"><span class="caption">{{ row.protected ? '管理员入口，始终保留' : parentHidden(row) ? '随上级菜单隐藏' : !row.visible ? '已隐藏' : row.disabled ? '显示为未接入模块' : '按账号权限显示' }}</span></template></el-table-column>
      </el-table>
    </div>
    </PageContainer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import PageContainer from '../components/PageContainer.vue';
import { api } from '../api';
import { refresh } from '../store/session';
const rows = ref([]);
const revision = ref(0);
const loading = ref(true);
const saving = ref(false);
const original = ref('[]');
const loaded = ref(false);

/* 后端返回的树直接喂给 el-table：无子项时把 children 置空，避免渲染出空展开箭头 */
function normalize(list, parentId = null) {
  return (list || []).map(item => ({
    ...item, parentId, visible: !!item.visible,
    children: item.children?.length ? normalize(item.children, item.id) : undefined,
  }));
}
const flat = () => rows.value.flatMap(row => [row, ...(row.children || [])]);
const snapshot = () => JSON.stringify(flat().map(row => [row.id, row.visible]).sort((a, b) => a[0] - b[0]));
const dirty = computed(() => loaded.value && snapshot() !== original.value);
function parentHidden(row) {
  return !!row.parentId && !flat().find(item => item.id === row.parentId)?.visible;
}
function setVisible(row, value) { row.visible = value; }
function apply(result) {
  revision.value = result.revision;
  if (result.menus) rows.value = normalize(result.menus);
  original.value = snapshot();
  loaded.value = true;
}
async function load() {
  loading.value = true;
  try { apply(await api('system/menus')); }
  catch (error) { ElMessage.error(error.message || '读取菜单设置失败'); }
  finally { loading.value = false; }
}
async function save() {
  if (!dirty.value || saving.value) return;
  saving.value = true;
  try {
    const result = await api('system/menus', { revision: revision.value, menus: flat().map(row => ({ id: row.id, visible: row.visible })) });
    apply(result);
    ElMessage.success('菜单设置已保存');
    // 重新取一次 /api/state，侧栏按新目录立即重绘
    await refresh();
  } catch (error) { ElMessage.error(error.message || '保存菜单设置失败'); }
  finally { saving.value = false; }
}
async function restoreDefaults() {
  if (loading.value || saving.value) return;
  saving.value = true;
  try {
    apply(await api('system/menus', { action: 'reset' }));
    ElMessage.success('已恢复默认显示');
    await refresh();
  } catch (error) { ElMessage.error(error.message || '恢复默认失败'); }
  finally { saving.value = false; }
}
onMounted(load);
</script>
<style scoped>
.menu-note { margin-bottom: 14px; line-height: 1.8; }
.menu-tag { margin-left: 10px; }
</style>
