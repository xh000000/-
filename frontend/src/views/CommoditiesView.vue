<template>
  <div>
    <PageHead title="品种管理" description="品种用于研报选题与章节关联，两级结构：板块 → 期货品种（带合约代码）；停用的品种不能再用于新建报告。">
      <el-button type="primary" @click="openDialog(null)">添加品种</el-button>
    </PageHead>

    <div class="panel">
      <el-table :data="tree" row-key="id" default-expand-all :tree-props="{ children: 'children' }" empty-text="暂无品种">
        <el-table-column label="品种 / 板块" min-width="240">
          <template #default="{ row }">
            <el-tag v-if="row.depth === 1" size="small" type="info" effect="plain" disable-transitions>板块</el-tag>
            <span :style="{ marginLeft: row.depth === 1 ? '6px' : '0' }">{{ row.name }}</span>
            <span v-if="row.children?.length" class="caption" style="margin-left: 8px">{{ row.children.length }} 个品种</span>
          </template>
        </el-table-column>
        <el-table-column label="合约代码" width="180">
          <template #default="{ row }">
            <code v-if="row.code" class="commodity-code">{{ row.code }}</code>
            <span v-else class="caption">—</span>
          </template>
        </el-table-column>
        <el-table-column label="层级" width="86">
          <template #default="{ row }">{{ row.depth }} 级</template>
        </el-table-column>
        <el-table-column label="状态" width="96">
          <template #default="{ row }">
            <el-tag :type="row.effective_enabled ? 'success' : 'info'" size="small" disable-transitions>
              {{ row.effective_enabled ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="visible" :title="form.id ? '编辑品种' : '添加品种'" width="480px" @closed="reset">
      <el-form label-width="96px" @submit.prevent="save">
        <el-form-item label="名称">
          <el-input v-model="form.name" maxlength="40" placeholder="如：螺纹钢 / 黑色" />
        </el-form-item>
        <el-form-item label="上级板块">
          <el-select v-model="form.parent_id" clearable placeholder="无 · 一级板块" style="width: 100%">
            <el-option
              v-for="item in parentOptions"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="合约代码">
          <el-input v-model="form.code" maxlength="40" placeholder="如 CU、I、IF/IH/IC/IM，可留空" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <p class="caption">品种仅支持两级；已有子品种的板块不能直接改为二级品种。合约代码用于研报核对（如 CU 对应沪铜）。</p>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import PageHead from '../components/PageHead.vue';
import { api } from '../api';
import { commodities, refresh } from '../store/session';

const busy = ref(false);
const visible = ref(false);
const form = reactive({ id: null, name: '', code: '', parent_id: null, enabled: true });

const source = computed(() =>
  commodities.value.map(item => ({ ...item, enabled: Boolean(item.enabled), parent_id: item.parent_id || null }))
);

/* 后端只存 parent_id，这里补出层级与父级生效状态，便于表格展示。 */
const tree = computed(() => {
  const map = new Map(source.value.map(item => [item.id, { ...item, depth: item.parent_id ? 2 : 1, children: [] }]));
  const roots = [];
  source.value.forEach(item => {
    const copy = map.get(item.id);
    const parent = item.parent_id ? map.get(item.parent_id) : null;
    if (parent) parent.children.push(copy);
    else roots.push(copy);
  });
  const finalize = list => {
    list.forEach(item => {
      item.children.sort((a, b) => a.id - b.id);
      item.effective_enabled = item.enabled && !(item.parent_id && !map.get(item.parent_id).enabled);
      finalize(item.children);
    });
  };
  finalize(roots);
  return roots;
});

const parentOptions = computed(() =>
  source.value.filter(item => !item.parent_id && item.id !== form.id && !hasChildren(item.id))
);

const hasChildren = id => source.value.some(item => item.parent_id === id);

function openDialog(row) {
  form.id = row?.id ?? null;
  form.name = row?.name || '';
  form.code = row?.code || '';
  form.parent_id = row?.parent_id ?? null;
  form.enabled = row ? Boolean(row.enabled) : true;
  visible.value = true;
}

function reset() {
  form.id = null;
  form.name = '';
  form.code = '';
  form.parent_id = null;
  form.enabled = true;
}

async function save() {
  const name = form.name.trim();
  if (!name) return ElMessage.warning('请填写品种名称');
  busy.value = true;
  try {
    await api('catalog', {
      kind: 'commodities',
      id: form.id,
      name,
      code: form.code.trim().toUpperCase(),
      parent_id: form.parent_id || null,
      enabled: form.enabled,
    });
    await refresh();
    visible.value = false;
    ElMessage.success('品种已保存');
  } catch (error) {
    ElMessage.error(error.message || '保存失败');
  } finally {
    busy.value = false;
  }
}
</script>
