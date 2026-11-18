<template>
  <div>
    <PageHead title="部门管理" description="部门最多两级（部门 → 分组）；账号归属到部门或分组，禁用后无法登录，已登录会话立即失效。">
      <el-button @click="openDept(null)">新建部门</el-button>
      <el-button type="primary" @click="openUser(null)">添加用户</el-button>
    </PageHead>

    <div class="panel">
      <div class="panel-header">
        <h3>部门与分组</h3>
        <span class="hint">共 {{ departments.length }} 个</span>
      </div>
      <el-table :data="deptRows" row-key="id" default-expand-all :tree-props="{ children: 'children' }" empty-text="暂无部门">
        <el-table-column label="部门 / 分组" min-width="240">
          <template #default="{ row }">
            <el-tag v-if="row.depth === 1" size="small" type="info" effect="plain" disable-transitions>部门</el-tag>
            <el-tag v-else size="small" effect="plain" disable-transitions>分组</el-tag>
            <span style="margin-left: 6px">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="层级" width="80">
          <template #default="{ row }">{{ row.depth }} 级</template>
        </el-table-column>
        <el-table-column label="账号数" width="86" prop="users" />
        <el-table-column label="排序" width="76" prop="sort_order" />
        <el-table-column label="状态" width="92">
          <template #default="{ row }">
            <el-tag :type="row.effective_enabled ? 'success' : 'info'" size="small" disable-transitions>
              {{ row.effective_enabled ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDept(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="removeDept(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="panel">
      <div class="panel-header">
        <h3>账号列表</h3>
        <span class="hint">共 {{ users.length }} 个账号</span>
      </div>
      <el-table :data="users" empty-text="暂无账号">
        <el-table-column label="姓名" min-width="120" prop="name" />
        <el-table-column label="角色" min-width="140">
          <template #default="{ row }">
            {{ row.role_name || ROLE_NAMES[row.role] || row.role }}
          </template>
        </el-table-column>
        <el-table-column label="部门" min-width="140">
          <template #default="{ row }">{{ row.dept_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="手机" width="130">
          <template #default="{ row }">{{ row.phone || '—' }}</template>
        </el-table-column>
        <el-table-column label="职务" min-width="120">
          <template #default="{ row }">{{ row.title || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="88">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small" disable-transitions>
              {{ row.enabled ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近登录" width="150">
          <template #default="{ row }">{{ localTime(row.last_login_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openUser(row)">编辑</el-button>
            <el-button link type="primary" size="small" @click="openReset(row)">重置密码</el-button>
            <el-button link :type="row.enabled ? 'danger' : 'success'" size="small" @click="toggleUser(row)">
              {{ row.enabled ? '禁用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 部门 -->
    <el-dialog v-model="deptVisible" :title="deptForm.id ? '编辑部门' : '新建部门'" width="480px" @closed="resetDept">
      <el-form label-width="96px" @submit.prevent="saveDept">
        <el-form-item label="名称">
          <el-input v-model="deptForm.name" maxlength="40" placeholder="如：黑色研究部 / 钢材组" />
        </el-form-item>
        <el-form-item label="上级部门">
          <el-select v-model="deptForm.parent_id" clearable placeholder="无 · 一级部门" style="width: 100%">
            <el-option v-for="item in topDepartments" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="deptForm.sort_order" controls-position="right" style="width: 100%" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="deptForm.enabled" />
        </el-form-item>
      </el-form>
      <p class="caption">部门最多两级，分组下不能再建分组；同级不允许重名。</p>
      <template #footer>
        <el-button @click="deptVisible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="saveDept">保存</el-button>
      </template>
    </el-dialog>

    <!-- 用户 -->
    <el-dialog v-model="userVisible" :title="userForm.id ? '编辑账号' : '添加用户'" width="560px" @closed="resetUser">
      <el-form label-width="96px" @submit.prevent="saveUser">
        <el-form-item label="姓名">
          <el-input v-model="userForm.name" maxlength="40" />
        </el-form-item>
        <el-form-item v-if="!userForm.id" label="初始密码">
          <el-input v-model="userForm.password" type="password" show-password placeholder="至少 6 位" autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="userForm.role_id" style="width: 100%">
            <el-option
              v-for="one in roles"
              :key="one.id"
              :label="`${one.name}（${ROLE_NAMES[one.base_role] || one.base_role}）`"
              :value="one.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="部门">
          <el-select v-model="userForm.dept_id" clearable placeholder="未分配" style="width: 100%">
            <el-option
              v-for="one in departments"
              :key="one.id"
              :label="(one.parent_name ? one.parent_name + ' / ' : '') + one.name"
              :value="one.id"
            />
          </el-select>
        </el-form-item>
        <div class="form-row">
          <el-form-item label="手机号" label-width="96px" style="flex: 1 1 200px">
            <el-input v-model="userForm.phone" maxlength="20" />
          </el-form-item>
          <el-form-item label="职务" label-width="64px" style="flex: 1 1 180px">
            <el-input v-model="userForm.title" maxlength="40" />
          </el-form-item>
        </div>
        <el-form-item label="启用账号">
          <el-switch v-model="userForm.enabled" />
        </el-form-item>
      </el-form>
      <p class="caption">角色决定可访问的菜单与审批资格；管理员账号不能停用自己，系统至少保留一个可用管理员。</p>
      <template #footer>
        <el-button @click="userVisible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="saveUser">保存</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码 -->
    <el-dialog v-model="resetVisible" title="重置密码" width="420px" @closed="resetForm.password = ''">
      <p class="caption" style="margin-bottom: 12px">
        为 <b>{{ resetForm.name }}</b> 设置新密码；保存后该账号的全部登录会话立即失效。
      </p>
      <el-form label-width="84px" @submit.prevent="saveReset">
        <el-form-item label="新密码">
          <el-input v-model="resetForm.password" type="password" show-password placeholder="至少 6 位" autocomplete="new-password" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="saveReset">确认重置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import PageHead from '../components/PageHead.vue';
import { api } from '../api';
import { departments, refresh, roles, user as me, users } from '../store/session';
import { ROLE_NAMES, localTime } from '../utils/format';

const busy = ref(false);

/* ---------- 部门 ---------- */
const deptRows = computed(() => {
  const map = new Map(
    departments.value.map(item => [item.id, { ...item, children: [] }])
  );
  const roots = [];
  departments.value.forEach(item => {
    const copy = map.get(item.id);
    const parent = item.parent_id ? map.get(item.parent_id) : null;
    if (parent) parent.children.push(copy);
    else roots.push(copy);
  });
  const sort = list => {
    list.sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0) || a.id - b.id);
    list.forEach(item => sort(item.children));
  };
  sort(roots);
  return roots;
});

const topDepartments = computed(() => departments.value.filter(item => !item.parent_id));

const deptVisible = ref(false);
const deptForm = reactive({ id: null, name: '', parent_id: null, sort_order: 0, enabled: true });

function openDept(row) {
  deptForm.id = row?.id ?? null;
  deptForm.name = row?.name || '';
  deptForm.parent_id = row?.parent_id ?? null;
  deptForm.sort_order = row?.sort_order ?? 0;
  deptForm.enabled = row ? Boolean(row.enabled) : true;
  deptVisible.value = true;
}

function resetDept() {
  deptForm.id = null;
  deptForm.name = '';
  deptForm.parent_id = null;
  deptForm.sort_order = 0;
  deptForm.enabled = true;
}

async function saveDept() {
  const name = deptForm.name.trim();
  if (!name) return ElMessage.warning('请填写部门名称');
  busy.value = true;
  try {
    await api('departments', {
      action: deptForm.id ? 'update' : 'create',
      id: deptForm.id,
      name,
      parent_id: deptForm.parent_id || null,
      sort_order: deptForm.sort_order || 0,
      enabled: deptForm.enabled,
    });
    await refresh();
    deptVisible.value = false;
    ElMessage.success('部门已保存');
  } catch (error) {
    ElMessage.error(error.message || '保存失败');
  } finally {
    busy.value = false;
  }
}

async function removeDept(row) {
  try {
    await ElMessageBox.confirm('删除前需先清空下级分组与该部门下的账号。', `删除「${row.name}」`, {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    });
  } catch {
    return;
  }
  try {
    await api('departments', { action: 'delete', id: row.id });
    await refresh();
    ElMessage.success('部门已删除');
  } catch (error) {
    ElMessage.error(error.message || '删除失败');
  }
}

/* ---------- 用户 ---------- */
const userVisible = ref(false);
const userForm = reactive({
  id: null, name: '', password: '', role_id: null, dept_id: null, phone: '', title: '', enabled: true,
});

function openUser(row) {
  userForm.id = row?.id ?? null;
  userForm.name = row?.name || '';
  userForm.password = '';
  userForm.role_id = row?.role_id ?? roles.value[0]?.id ?? null;
  userForm.dept_id = row?.dept_id ?? null;
  userForm.phone = row?.phone || '';
  userForm.title = row?.title || '';
  userForm.enabled = row ? Boolean(row.enabled) : true;
  userVisible.value = true;
}

function resetUser() {
  userForm.id = null;
  userForm.name = '';
  userForm.password = '';
  userForm.role_id = null;
  userForm.dept_id = null;
  userForm.phone = '';
  userForm.title = '';
  userForm.enabled = true;
}

async function saveUser() {
  if (!userForm.name.trim()) return ElMessage.warning('请填写姓名');
  if (!userForm.role_id) return ElMessage.warning('请选择角色');
  if (!userForm.id && userForm.password.length < 6) return ElMessage.warning('初始密码至少 6 位');
  busy.value = true;
  try {
    await api('users', {
      action: userForm.id ? 'update' : 'create',
      id: userForm.id,
      name: userForm.name.trim(),
      password: userForm.password,
      role_id: userForm.role_id,
      dept_id: userForm.dept_id || null,
      phone: userForm.phone.trim(),
      title: userForm.title.trim(),
      enabled: userForm.enabled,
    });
    await refresh();
    userVisible.value = false;
    ElMessage.success('账号已保存');
  } catch (error) {
    ElMessage.error(error.message || '保存失败');
  } finally {
    busy.value = false;
  }
}

async function toggleUser(row) {
  const self = row.id === me.value.id;
  if (self) return ElMessage.warning('不能停用自己的账号');
  try {
    await ElMessageBox.confirm(
      row.enabled ? '禁用后该账号无法登录，已登录会话立即失效。' : '启用后该账号可以重新登录。',
      `${row.enabled ? '禁用' : '启用'}「${row.name}」`,
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    );
  } catch {
    return;
  }
  try {
    await api('users', { action: 'toggle', id: row.id });
    await refresh();
    ElMessage.success('账号状态已更新');
  } catch (error) {
    ElMessage.error(error.message || '操作失败');
  }
}

const resetVisible = ref(false);
const resetForm = reactive({ id: null, name: '', password: '' });

function openReset(row) {
  resetForm.id = row.id;
  resetForm.name = row.name;
  resetForm.password = '';
  resetVisible.value = true;
}

async function saveReset() {
  if (resetForm.password.length < 6) return ElMessage.warning('密码至少 6 位');
  busy.value = true;
  try {
    await api('users', { action: 'reset', id: resetForm.id, password: resetForm.password });
    resetVisible.value = false;
    ElMessage.success('密码已重置，请通知本人使用新密码登录');
  } catch (error) {
    ElMessage.error(error.message || '重置失败');
  } finally {
    busy.value = false;
  }
}
</script>
