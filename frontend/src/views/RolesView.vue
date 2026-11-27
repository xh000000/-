<template>
  <div>
    <PageContainer title="角色管理">
      <template #actions>
        <el-button type="primary" @click="openDialog(null)">添加角色</el-button>
      </template>

    <div class="panel">
      <el-table :data="roles" empty-text="暂无角色">
        <el-table-column label="角色名称" min-width="160">
          <template #default="{ row }">
            {{ row.name }}
            <el-tag v-if="row.builtin" size="small" type="info" effect="plain" class="tag-gap" disable-transitions>内置</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="角色类型" width="120">
          <template #default="{ row }">{{ ROLE_NAMES[row.base_role] || row.base_role }}</template>
        </el-table-column>
        <el-table-column label="菜单权限" min-width="360">
          <template #default="{ row }">
            <template v-if="isAll(row)">
              <el-tag size="small" type="success" effect="plain" disable-transitions>全部权限</el-tag>
            </template>
            <template v-else>
              <el-tag
                v-for="key in row.menus"
                :key="key"
                size="small"
                effect="plain"
                class="tag-gap"
                disable-transitions
              >{{ key }}</el-tag>
              <span v-if="!row.menus.length" class="caption">无菜单权限</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="账号数" width="90" prop="users" />
        <el-table-column label="操作" width="130">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
            <el-button
              v-if="!row.builtin"
              link
              type="danger"
              size="small"
              @click="remove(row)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="visible" :title="form.id ? '编辑角色' : '添加角色'" width="560px" @closed="reset">
      <el-form label-width="96px" @submit.prevent="save">
        <el-form-item label="角色名称">
          <el-input v-model="form.name" maxlength="30" />
        </el-form-item>
        <el-form-item label="角色类型">
          <el-select v-model="form.base_role" :disabled="form.builtin" style="width: 100%">
            <el-option v-for="item in BASE_ROLES" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="菜单权限">
          <el-checkbox-group v-model="form.menus" class="menu-checks">
            <el-checkbox v-for="key in MENU_KEYS" :key="key" :value="key">{{ key }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="save">保存</el-button>
      </template>
    </el-dialog>
    </PageContainer>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import PageContainer from '../components/PageContainer.vue';
import { api } from '../api';
import { refresh, roles } from '../store/session';
import { MENU_KEYS, ROLE_NAMES } from '../utils/format';

const BASE_ROLES = [
  { value: 'researcher', label: '研究员' },
  { value: 'reviewer', label: '研究复核' },
  { value: 'compliance', label: '合规审核' },
  { value: 'publisher', label: '发布专员' },
  { value: 'admin', label: '管理员' },
];

const busy = ref(false);
const visible = ref(false);
const form = reactive({ id: null, name: '', base_role: 'researcher', menus: [], builtin: false });

const isAll = row => row.menus.includes('*');

function openDialog(row) {
  form.id = row?.id ?? null;
  form.name = row?.name || '';
  form.base_role = row?.base_role || 'researcher';
  form.menus = row && !isAll(row) ? [...row.menus] : row && isAll(row) ? [] : [...MENU_KEYS];
  form.builtin = Boolean(row?.builtin);
  visible.value = true;
}

function reset() {
  form.id = null;
  form.name = '';
  form.base_role = 'researcher';
  form.menus = [];
  form.builtin = false;
}

async function save() {
  const name = form.name.trim();
  if (!name) return ElMessage.warning('请填写角色名称');
  if (form.base_role !== 'admin' && !form.menus.length) {
    return ElMessage.warning('至少选择一项菜单权限，或改为管理员类型');
  }
  busy.value = true;
  try {
    await api('roles', {
      action: form.id ? 'update' : 'create',
      id: form.id,
      name,
      base_role: form.base_role,
      menus: form.base_role === 'admin' ? ['*'] : form.menus,
    });
    await refresh();
    visible.value = false;
    ElMessage.success('角色已保存');
  } catch (error) {
    ElMessage.error(error.message || '保存失败');
  } finally {
    busy.value = false;
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm('该角色下仍有账号时不能删除，请先调整账号角色。', `删除「${row.name}」`, {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    });
  } catch {
    return;
  }
  try {
    await api('roles', { action: 'delete', id: row.id });
    await refresh();
    ElMessage.success('角色已删除');
  } catch (error) {
    ElMessage.error(error.message || '删除失败');
  }
}
</script>

<style scoped>
.tag-gap { margin-left: 6px; }
.menu-checks { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 2px 8px; width: 100%; }
</style>
