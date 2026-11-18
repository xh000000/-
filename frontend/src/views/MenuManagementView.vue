<template>
  <div>
    <PageHead title="菜单管理" description="统一控制侧边菜单的显示与隐藏，仅管理员可配置。">
      <el-button :disabled="loading || saving" @click="restoreDefaults">恢复默认</el-button>
      <el-button :loading="loading" :disabled="saving" @click="load">重新加载</el-button>
      <el-button type="primary" :loading="saving" :disabled="loading || !dirty" @click="save">保存设置</el-button>
    </PageHead>
    <el-alert type="info" :closable="false" show-icon class="menu-note"
      title="隐藏上级菜单会同时隐藏其下所有菜单；显示开关不改变账号权限。系统设置和菜单管理保留管理员入口，方便恢复设置。" />
    <div class="panel">
      <div class="panel-header"><h3>菜单显示设置</h3><span class="caption">{{ dirty ? '有未保存的修改' : '保存后当前页面立即生效，其他已打开页面刷新后生效' }}</span></div>
      <el-table v-loading="loading" :data="rows" row-key="id" default-expand-all max-height="650">
        <el-table-column label="菜单名称" min-width="200">
          <template #default="{ row }"><span>{{ row.label }}</span><el-tag v-if="row.admin" size="small" type="info" effect="plain" class="menu-tag">仅管理员</el-tag></template>
        </el-table-column>
        <el-table-column label="页面路径" min-width="200"><template #default="{ row }"><span class="caption">{{ row.path || (row.children ? '菜单分组' : '暂未接入') }}</span></template></el-table-column>
        <el-table-column label="显示" width="110" align="center">
          <template #default="{ row }"><el-switch :model-value="visibility[row.id] !== false" :disabled="loading || saving || row.protected || parentHidden(row)"
            :aria-label="`${row.label}显示开关`" @update:model-value="value => setVisible(row.id, value)" /></template>
        </el-table-column>
        <el-table-column label="说明" min-width="200"><template #default="{ row }"><span class="caption">{{ row.protected ? '管理员入口，始终保留' : parentHidden(row) ? '随上级菜单隐藏' : visibility[row.id] === false ? '已隐藏' : row.disabled ? '显示为未接入模块' : '按账号权限显示' }}</span></template></el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import PageHead from '../components/PageHead.vue';
import { MENU, menuId, PROTECTED_MENU_IDS } from '../utils/menu';
import { api } from '../api';
import { refresh, session } from '../store/session';
const visibility = reactive({});
const revision = ref(0);
const loading = ref(true);
const saving = ref(false);
const original = ref('{}');
const loaded = ref(false);
const rows = MENU.map(group => ({ ...group, id: menuId(group), protected: PROTECTED_MENU_IDS.includes(menuId(group)),
  children: group.children?.map(child => ({ ...child, id: menuId(child, group), parentId: menuId(group),
    admin: child.admin || group.admin, disabled: child.disabled || group.disabled,
    protected: PROTECTED_MENU_IDS.includes(menuId(child, group)) })) }));
const normalized = () => JSON.stringify(Object.fromEntries(Object.entries(visibility).filter(([, v]) => v === false).sort(([a], [b]) => a.localeCompare(b))));
const dirty = computed(() => loaded.value && normalized() !== original.value);
const parentHidden = row => row.parentId && visibility[row.parentId] === false;
function setVisible(id, value) { if (value) delete visibility[id]; else visibility[id] = false; }
function replace(next) { Object.keys(visibility).forEach(key => delete visibility[key]); Object.assign(visibility, next); }
function restoreDefaults() { if (loaded.value) replace({}); }
async function load() {
  loading.value = true;
  try {
    const result = await api('system/menus');
    replace(result.visibility || {}); revision.value = result.revision; original.value = normalized(); loaded.value = true;
  } catch (error) { ElMessage.error(error.message || '读取菜单设置失败'); }
  finally { loading.value = false; }
}
async function save() {
  if (!dirty.value || saving.value) return;
  saving.value = true;
  try {
    const result = await api('system/menus', { revision: revision.value, visibility: { ...visibility } });
    replace(result.visibility || {}); revision.value = result.revision; original.value = normalized();
    if (session.data) session.data.menu_visibility = result.visibility;
    ElMessage.success('菜单显示设置已保存');
    // Refresh role and navigation state without requiring a page reload.
    await refresh();
  } catch (error) { ElMessage.error(error.message || '保存菜单设置失败'); }
  finally { saving.value = false; }
}
onMounted(load);
</script>
<style scoped>
.menu-note { margin-bottom: 18px; }
.menu-tag { margin-left: 10px; }
</style>
