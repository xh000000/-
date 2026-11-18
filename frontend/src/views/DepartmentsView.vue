<template>
  <div>
    <PageHead title="部门管理" description="维护部门与分组，最多支持两级结构（部门 → 分组）。">
      <el-button type="primary" @click="openDept(null)">新建部门</el-button>
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

  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import PageHead from '../components/PageHead.vue';
import { api } from '../api';
import { departments, refresh } from '../store/session';

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

</script>
