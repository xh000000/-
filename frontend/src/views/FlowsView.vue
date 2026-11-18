<template>
  <div>
    <PageHead
      title="审批流配置"
      description="为指定分类配置多节点审批流；新建报告时按分类匹配并快照，未匹配的分类沿用分类自带的审批节点。"
    >
      <el-button type="primary" @click="openDialog(null)">添加审批流</el-button>
    </PageHead>

    <div class="panel">
      <el-table :data="flows" empty-text="暂无审批流">
        <el-table-column label="名称" min-width="140" prop="name" />
        <el-table-column label="关联分类" min-width="220">
          <template #default="{ row }">
            <template v-if="row.category_ids.length">
              <el-tag
                v-for="id in row.category_ids"
                :key="id"
                size="small"
                effect="plain"
                class="tag-gap"
                disable-transitions
              >{{ categoryName(id) }}</el-tag>
            </template>
            <span v-else class="caption">未关联（不生效）</span>
          </template>
        </el-table-column>
        <el-table-column label="节点顺序" min-width="280">
          <template #default="{ row }">
            <span v-for="(node, index) in row.nodes" :key="index" class="node-chip">
              {{ node.label }}<em>{{ MODE_NAMES[node.mode] || node.mode }}</em><i v-if="index < row.nodes.length - 1">→</i>
            </span>
            <span class="node-chip node-final">发布</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="92">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small" disable-transitions>
              {{ row.enabled ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="visible" :title="form.id ? '编辑审批流' : '添加审批流'" width="720px" @closed="reset">
      <el-form label-width="96px" @submit.prevent="save">
        <el-form-item label="审批流名称">
          <el-input v-model="form.name" maxlength="40" />
        </el-form-item>
        <el-form-item label="关联分类">
          <el-select v-model="form.category_ids" multiple collapse-tags placeholder="不选表示不生效" style="width: 100%">
            <el-option v-for="item in leafCategories" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>

      <div class="panel-header" style="margin-top: 4px">
        <h3>审批节点</h3>
        <el-button size="small" @click="addNode">添加节点</el-button>
      </div>

      <div v-for="(node, index) in form.nodes" :key="index" class="config-section">
        <div class="config-section-head">
          <b>节点 {{ index + 1 }}</b>
          <span>
            <el-button link size="small" :disabled="index === 0" @click="moveNode(index, -1)">↑</el-button>
            <el-button link size="small" :disabled="index === form.nodes.length - 1" @click="moveNode(index, 1)">↓</el-button>
            <el-button link type="danger" size="small" :disabled="form.nodes.length === 1" @click="removeNode(index)">删除</el-button>
          </span>
        </div>
        <div class="form-row">
          <el-form-item label="节点名称" label-width="72px" style="flex: 1 1 160px">
            <el-input v-model="node.label" maxlength="30" />
          </el-form-item>
          <el-form-item label="角色" label-width="52px" style="flex: 1 1 140px">
            <el-select v-model="node.role" style="width: 100%" @change="node.users = []">
              <el-option label="研究复核" value="reviewer" />
              <el-option label="合规审核" value="compliance" />
            </el-select>
          </el-form-item>
          <el-form-item label="方式" label-width="52px" style="flex: 1 1 140px">
            <el-select v-model="node.mode" style="width: 100%">
              <el-option v-for="(name, key) in MODE_NAMES" :key="key" :label="name" :value="key" />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item label="指定审批人" label-width="86px">
          <el-select v-model="node.users" multiple placeholder="留空表示该角色任一账号可签" style="width: 100%">
            <el-option v-for="one in roleUsers(node.role)" :key="one.id" :label="one.name" :value="one.id" />
          </el-select>
        </el-form-item>
      </div>

      <p class="caption">审批流必须包含一个合规审核节点；会签与依次审批必须指定审批人。作者不能审核或发布自己的报告。</p>

      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import PageHead from '../components/PageHead.vue';
import { api } from '../api';
import { categoryTree, flows, refresh, users } from '../store/session';
import { MODE_NAMES } from '../utils/format';

const busy = ref(false);
const visible = ref(false);
const form = reactive({ id: null, name: '', category_ids: [], nodes: [], enabled: true });

const leafCategories = computed(() => categoryTree.value.filter(item => !item.folder));
const categoryName = id => categoryTree.value.find(item => item.id === id)?.name || '#' + id;
const roleUsers = role => users.value.filter(item => item.role === role);

function openDialog(row) {
  form.id = row?.id ?? null;
  form.name = row?.name || '';
  form.category_ids = row ? [...row.category_ids] : [];
  form.nodes = row
    ? row.nodes.map(node => ({ ...node, users: [...(node.users || [])] }))
    : [{ label: '研究复核', role: 'reviewer', mode: 'any', users: [] }];
  form.enabled = row ? Boolean(row.enabled) : true;
  visible.value = true;
}

function reset() {
  form.id = null;
  form.name = '';
  form.category_ids = [];
  form.nodes = [];
  form.enabled = true;
}

function addNode() {
  form.nodes.push({ label: '合规审核', role: 'compliance', mode: 'any', users: [] });
}

function removeNode(index) {
  if (form.nodes.length === 1) return;
  form.nodes.splice(index, 1);
}

function moveNode(index, delta) {
  const target = index + delta;
  if (target < 0 || target >= form.nodes.length) return;
  [form.nodes[index], form.nodes[target]] = [form.nodes[target], form.nodes[index]];
}

async function save() {
  const name = form.name.trim();
  if (!name) return ElMessage.warning('请填写审批流名称');
  if (!form.nodes.length) return ElMessage.warning('至少配置一个审批节点');
  if (!form.nodes.some(node => node.role === 'compliance')) {
    return ElMessage.warning('审批流必须包含一个合规审核节点');
  }
  const invalid = form.nodes.find(node => node.mode !== 'any' && !(node.users || []).length);
  if (invalid) return ElMessage.warning(`节点「${invalid.label}」为${MODE_NAMES[invalid.mode]}，必须指定审批人`);

  busy.value = true;
  try {
    await api('approval-flows', {
      action: form.id ? 'update' : 'create',
      id: form.id,
      name,
      category_ids: form.category_ids,
      nodes: form.nodes.map(node => ({ ...node, label: node.label.trim() || '审批节点' })),
      enabled: form.enabled,
    });
    await refresh();
    visible.value = false;
    ElMessage.success('审批流已保存');
  } catch (error) {
    ElMessage.error(error.message || '保存失败');
  } finally {
    busy.value = false;
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(
      `删除后，已按该审批流创建的报告不受影响（使用创建时的快照）。`,
      `删除审批流「${row.name}」`,
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    );
  } catch {
    return;
  }
  try {
    await api('approval-flows', { action: 'delete', id: row.id });
    await refresh();
    ElMessage.success('审批流已删除');
  } catch (error) {
    ElMessage.error(error.message || '删除失败');
  }
}
</script>

<style scoped>
.node-chip { font-size: 12.5px; color: var(--el-text-color-regular); }
.node-chip em { font-style: normal; color: var(--el-text-color-secondary); margin-left: 4px; }
.node-chip i { font-style: normal; color: var(--el-text-color-placeholder); margin: 0 6px; }
.node-chip.node-final::before { content: '→'; color: var(--el-text-color-placeholder); margin-right: 6px; }
.tag-gap { margin-right: 6px; }
</style>
