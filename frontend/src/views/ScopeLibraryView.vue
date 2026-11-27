<template>
  <div>
    <PageContainer title="指标管理">
      <template #actions>
        <el-button type="primary" @click="openAdd()">新增指标</el-button>
      </template>
      <div class="panel">
        <el-table
          ref="tableRef"
          :data="treeRows"
          v-loading="loading"
          row-key="id"
          :default-expand-all="expanded"
          :tree-props="{ children: 'children' }"
          empty-text="暂无指标"
          size="small"
          border
          @header-dragend="onHeaderDragend"
        >
          <el-table-column label="分组 / 指标名" min-width="240">
            <template #default="{ row }">
              <template v-if="row.isGroup">
                <span class="lib-group-name">{{ row.group }}</span>
                <span class="caption" style="margin-left: 8px">{{ row.count }} 项</span>
              </template>
              <template v-else>{{ row.name }}</template>
            </template>
          </el-table-column>
          <el-table-column label="编码" width="110">
            <template #default="{ row }">
              <span class="caption lib-code">{{ row.code }}</span>
            </template>
          </el-table-column>
          <el-table-column label="品种" width="110">
            <template #default="{ row }">
              <span v-if="row.isGroup" class="caption">—</span>
              <span v-else-if="row.commodity" class="caption">{{ row.commodity }}</span>
              <span v-else class="caption lib-unclassified">未识别</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="130" align="right">
            <template #default="{ row }">
              <template v-if="row.isGroup">
                <el-button
                  link type="primary" size="small" :disabled="row.builtin"
                  :title="row.builtin ? '系统分组不可改名' : '重命名分组'" @click="openGroupForm(row)"
                >编辑</el-button>
                <el-button
                  link type="danger" size="small" :disabled="row.builtin"
                  :title="row.builtin ? '系统分组不可删除' : (row.count ? `删除分组及组内 ${row.count} 个指标` : '删除空分组')"
                  @click="removeGroup(row)"
                >删除</el-button>
              </template>
              <template v-else>
                <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
                <el-button link type="danger" size="small" @click="removeOne(row)">删除</el-button>
              </template>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </PageContainer>

    <!-- 一个弹窗覆盖三种落点：新增指标、编辑指标、新建/重命名分组。
         卡片永远按树的形状摆——一级在上、二级缩进在下；哪种模式就只显示对应层级。 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="500px" @closed="resetDialog">
      <div class="lib-treeform">
        <div class="lib-treeform-node is-parent">
          <div class="lib-treeform-label">{{ mode === 'group' ? '分组名' : '归入分组' }}</div>
          <el-input
            v-if="mode === 'group'"
            v-model="form.group" maxlength="20" show-word-limit
            placeholder="如 基差、利润、进出口"
            @keyup.enter="submit"
          />
          <el-select
            v-else
            v-model="form.group" filterable allow-create default-first-option
            placeholder="请选择分组，或输入新分组名" style="width: 100%"
          >
            <el-option v-for="group in groups" :key="group" :label="group" :value="group" />
          </el-select>
          <div v-if="mode === 'group'" class="lib-code-row">
            <span class="lib-code-label">编码</span>
            <el-input
              v-model="form.code" maxlength="20" placeholder="留空自动生成，如 GRP00007"
              @input="form.code = normalizeCodeInput(form.code)"
            />
          </div>
          <!-- 新增指标时一级也可能顺带新建分组，分组编码同样可以在这里定 -->
          <div v-else class="lib-code-row">
            <span class="lib-code-label">编码</span>
            <el-input
              v-model="groupCodeInput" maxlength="20"
              :disabled="!newGroupName"
              :placeholder="newGroupName ? '留空自动生成，如 GRP00007' : (form.group.trim() ? '沿用该分组现有编码' : '先选或填写分组')"
              @input="form.groupCode = normalizeCodeInput(form.groupCode)"
            />
          </div>
          <p v-if="groupCodeInvalid" class="caption lib-warn">分组编码只能用字母、数字与 _ - /，2-20 位</p>
          <p v-if="mode === 'group' && form.groupId" class="caption">只改分组本身，组内 {{ groupItemCount }} 个指标不受影响。</p>
          <p v-else-if="mode === 'group'" class="caption">先建目录、之后再往里加指标也可以。</p>
          <p v-else-if="mode === 'edit' && form.group.trim() !== form.originGroup" class="caption lib-newgroup">
            保存后这条指标会移到{{ newGroupName ? '新分组' : '分组' }}「{{ form.group }}」
          </p>
          <p v-else-if="mode === 'edit'" class="caption">换一个分组即可把这条指标移过去，编码不变。</p>
          <p v-else-if="newGroupName" class="caption lib-newgroup">该分组还不存在，提交时一并创建；编码留空则自动生成。</p>
          <p v-else-if="existingGroup" class="caption">指标会挂在已有分组下，分组编码不变。</p>
          <p v-else class="caption">表格的第一层目录，输入新名称回车即新建。</p>
        </div>

        <div v-if="mode !== 'group'" class="lib-treeform-node is-child">
          <div class="lib-treeform-label">指标名</div>
          <el-select
            v-if="mode === 'add'"
            v-model="presetItems"
            multiple filterable allow-create default-first-option
            :reserve-keyword="false"
            placeholder="输入后回车，可连续输入多个"
            style="width: 100%"
          >
            <el-option v-for="item in presetItems" :key="item" :label="item" :value="item" />
          </el-select>
          <el-input v-else v-model="form.name" maxlength="60" placeholder="如 螺纹钢现货价" @keyup.enter="submit" />
          <div class="lib-code-row">
            <span class="lib-code-label">编码</span>
            <el-input
              v-model="form.code" maxlength="20"
              :disabled="bulkAdd"
              placeholder="留空自动生成，如 IND00088"
              @input="form.code = normalizeCodeInput(form.code)"
            />
          </div>
          <div class="lib-code-row">
            <span class="lib-code-label">品种</span>
            <el-tree-select
              v-model="form.commodity"
              :data="commodityTree"
              node-key="name"
              :props="{ label: 'name', children: 'children', disabled: 'disabled' }"
              check-strictly clearable filterable default-expand-all
              :render-after-expand="false"
              placeholder="留空则按名称自动识别"
              style="flex: 1; min-width: 0"
            />
          </div>
          <p v-if="bulkAdd" class="caption">一次新增多条时编码自动生成，之后可在编辑里逐条改。</p>
          <p v-else-if="codeInvalid" class="caption lib-warn">编码只能用字母、数字与 _ - /，2-20 位</p>
          <p v-if="mode === 'add' && invalidItems.length" class="caption lib-warn">
            含不支持的字符：{{ invalidItems.join('、') }}；只允许中文、字母、数字与 | . - _ / % ( ) 等
          </p>
          <p v-else-if="mode === 'add' && !presetItems.length" class="caption">挂在上面这个分组下的具体指标。</p>
          <p v-else-if="mode === 'edit' && !itemValid(form.name)" class="caption lib-warn">
            含不支持的字符，只允许中文、字母、数字与 | . - _ / % ( ) 等
          </p>
          <p v-else-if="mode === 'edit' && form.name.trim() !== form.origin" class="caption lib-newgroup">
            改名会同步更新历史数据与各数据源的引用，编码不变。
          </p>
        </div>
      </div>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="!canSubmit" @click="submit">{{ submitLabel }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import PageContainer from '../components/PageContainer.vue';
import { api } from '../api';
import { createResizeHandler } from '../utils/tableResize';
import { commodities } from '../store/session';

const library = ref([]);
const loading = ref(true);
const saving = ref(false);
const presetItems = ref([]);
const dialogVisible = ref(false);
/* 弹窗只有一个，靠 mode 决定显示哪几层：add=新增指标 / edit=编辑指标 / group=新建或重命名分组 */
const mode = ref('add');
const form = reactive({
  id: null, code: '', name: '', origin: '', originCode: '',
  group: '', originGroup: '', groupId: null, groupCode: '', commodity: '',
});

const groups = computed(() => library.value.map(group => group.group));

/* 品种树取自品种管理：板块为不可选的一级，品种为可选的二级；空板块不展示 */
const commodityTree = computed(() => {
  const list = commodities.value.map(item => ({ id: item.id, name: item.name, parent_id: item.parent_id || null }));
  const roots = list.filter(item => !item.parent_id).map(item => ({ ...item, children: [], disabled: true }));
  const byId = new Map(roots.map(item => [item.id, item]));
  list.filter(item => item.parent_id).forEach(item => {
    const parent = byId.get(item.parent_id);
    if (parent) parent.children.push({ ...item, children: [] });
  });
  return roots.filter(root => root.children.length);
});

/* 树形数据：分组=一级目录（有自己的 id），指标=二级子行（有自己的 id + 编码） */
const treeRows = computed(() => library.value.map(group => {
  const children = group.entries.map(entry => ({
    id: `i:${entry.id}`, indicatorId: entry.id, isGroup: false,
    name: entry.name, item: entry.name, code: entry.code, commodity: entry.commodity,
    group: group.group, groupId: group.id,
  }));
  return {
    id: `g:${group.id}`, groupId: group.id, isGroup: true, code: group.code || '',
    group: group.group, builtin: group.builtin, count: children.length, children,
  };
}));

/* 默认折叠：一屏就能看到全部分组，需要看明细时点行首箭头展开 */
const expanded = ref(false);
const tableRef = ref(null);

/* 任何影响行结构的状态变化后强制重排，兜底列宽 flex 分配 */
watch([treeRows, expanded], () => {
  nextTick(() => tableRef.value?.doLayout());
});

/* 列宽拖拽：被拖列保留宽度，另选一列吸收剩余宽度（避免右侧留白又不弹回原宽） */
const onHeaderDragend = createResizeHandler(tableRef);

/* 与后端 SCOPE_ITEM_RE 同规则的字符校验 */
const ITEM_RE = /^[\w\u4e00-\u9fa5|.\-/%()（）·、]+$/;
function itemValid(item) {
  const value = String(item || '').trim();
  return Boolean(value) && value.length <= 60 && ITEM_RE.test(value);
}

/* 编码规范与后端 CODE_RE 一致：字母数字加 _ - /，2-20 位；唯一性只能由后端判定 */
const CODE_RE = /^[A-Z0-9][A-Z0-9_\-/]{1,19}$/;
function normalizeCodeInput(value) {
  return String(value || '').toUpperCase();
}
const codeInvalid = computed(() => {
  const code = form.code.trim();
  return Boolean(code) && !CODE_RE.test(code);
});
/* 一级（分组）编码：只在「顺带新建分组」时可填；选的是已有分组就显示它的现有编码，只读 */
const groupCodeInvalid = computed(() => {
  const code = form.groupCode.trim();
  return Boolean(newGroupName.value && code) && !CODE_RE.test(code);
});
const groupCodeInput = computed({
  get: () => (newGroupName.value ? form.groupCode : (existingGroup.value?.code || '')),
  set: value => { form.groupCode = value; },
});
/* 批量新增时编码没法一条一个，交给后端自动生成 */
const bulkAdd = computed(() => mode.value === 'add' && presetItems.value.length > 1);
watch(() => presetItems.value.length, count => {
  if (mode.value === 'add' && count > 1) form.code = '';
});

/* 一级目录不做任何默认值或自动预判：归到哪个分组是指标的核心归属，必须由人明确指定。
   猜错了比让人多点一次下拉更难发现。 */
const invalidItems = computed(() => presetItems.value.filter(item => !itemValid(item)));

const canAdd = computed(() => presetItems.value.length > 0 && !invalidItems.value.length && Boolean(form.group.trim()));

/* 分组框里输入了库里没有的名字 → 提交时会新建分组，提前告知 */
const newGroupName = computed(() => {
  const group = form.group.trim();
  return group && !groups.value.includes(group) ? group : '';
});

/* 选中的是已有分组：只读展示它的编码，避免让人误以为能顺带改掉它 */
const existingGroup = computed(() => {
  const group = form.group.trim();
  return group ? library.value.find(item => item.group === group) : null;
});

const groupItemCount = computed(() => {
  const target = library.value.find(group => group.id === form.groupId);
  return target ? target.entries.length : 0;
});

/* 标题与按钮跟着「落点」走：用户在做什么，由他自己输入的内容决定，不用猜 */
const dialogTitle = computed(() => {
  if (mode.value === 'group') return form.groupId ? '重命名分组' : '新建分组';
  if (mode.value === 'edit') return '编辑指标';
  return newGroupName.value ? `新建分组「${newGroupName.value}」` : '新增指标';
});

const submitLabel = computed(() => {
  if (mode.value === 'group') return form.groupId ? '保存' : '创建';
  if (mode.value === 'edit') return '保存';
  const count = presetItems.value.length;
  if (!count) return '添加';
  if (newGroupName.value) return `新建分组并添加 ${count} 项`;
  return count > 1 ? `添加 ${count} 项` : '添加';
});

const canSubmit = computed(() => {
  if (codeInvalid.value || groupCodeInvalid.value) return false;
  if (mode.value === 'group') {
    const name = form.group.trim();
    if (!name || !itemValid(name)) return false;
    /* 新建：名字合法即可（编码可留空）；重命名：名字或编码至少改了一样 */
    return form.groupId ? (name !== form.origin || form.code.trim() !== (form.originCode || '')) : true;
  }
  if (mode.value === 'edit') return itemValid(form.name);
  return canAdd.value;
});

function submit() {
  if (!canSubmit.value) return;
  if (mode.value === 'group') saveGroup();
  else if (mode.value === 'edit') saveEdit();
  else addPreset();
}

function openAdd() {
  mode.value = 'add';
  presetItems.value = [];
  Object.assign(form, {
    id: null, code: '', name: '', origin: '', originCode: '', group: '', originGroup: '',
    groupId: null, groupCode: '', commodity: '',
  });
  dialogVisible.value = true;
}

function openEdit(row) {
  mode.value = 'edit';
  presetItems.value = [];
  Object.assign(form, {
    id: row.indicatorId, code: row.code, name: row.name, origin: row.name, originCode: row.code,
    group: row.group, originGroup: row.group, groupId: row.groupId, groupCode: '',
    commodity: row.commodity || '',
  });
  dialogVisible.value = true;
}

/* 一级行的「编辑」：重命名分组、改分组编码。
   新建分组不单设入口——在「新增指标」里输入一个库里没有的分组名，就同时建组。 */
function openGroupForm(row) {
  mode.value = 'group';
  presetItems.value = [];
  Object.assign(form, {
    id: null, code: row?.code || '', name: '', origin: row?.group || '', originCode: row?.code || '',
    group: row?.group || '', originGroup: row?.group || '', groupId: row?.groupId || null,
    groupCode: '', commodity: '',
  });
  dialogVisible.value = true;
}

function resetDialog() {
  presetItems.value = [];
  Object.assign(form, {
    id: null, code: '', name: '', origin: '', originCode: '', group: '', originGroup: '',
    groupId: null, groupCode: '', commodity: '',
  });
}

async function load() {
  loading.value = true;
  try {
    const result = await api('data/sources');
    library.value = result.scope_library || [];
  } catch (error) {
    ElMessage.error(error.message || '加载指标管理失败');
  } finally {
    loading.value = false;
  }
}

async function addPreset() {
  const items = [...new Set(presetItems.value.map(item => String(item).trim()).filter(Boolean))];
  if (!items.length) return ElMessage.warning('请输入指标名');
  if (items.some(item => !itemValid(item))) return ElMessage.warning('指标名含不支持的字符');
  const group = form.group.trim();
  if (!group) return ElMessage.warning('请选择或输入所属分组');
  const isNewGroup = !groups.value.includes(group);
  saving.value = true;
  try {
    /* 一次提交整批，后端逐个建主数据并回发最新树，不会出现「加了一半失败」。
       分组编码只在「顺带新建分组」时有意义，已有分组传了也会被后端忽略。 */
    const result = await api('data/scope-library', {
      group, items,
      code: bulkAdd.value ? undefined : (form.code.trim() || undefined),
      group_code: isNewGroup ? (form.groupCode.trim() || undefined) : undefined,
      commodity: form.commodity || undefined,
    });
    if (result?.library) library.value = result.library;
    dialogVisible.value = false;
    ElMessage.success(
      isNewGroup
        ? `已新建分组「${group}」，含 ${items.length} 个指标`
        : `已添加 ${items.length} 个指标到「${group}」`,
    );
  } catch (error) {
    ElMessage.error(error.message || '添加失败');
  } finally {
    saving.value = false;
  }
}

async function saveEdit() {
  const name = form.name.trim();
  if (!name || !itemValid(name)) return;
  saving.value = true;
  try {
    const result = await api('data/scope-library/update', {
      id: form.id, name, group: form.group || '其他',
      code: form.code.trim() || undefined,
      commodity: form.commodity || '',
    });
    library.value = result.library || [];
    dialogVisible.value = false;
    const moved = result.cascade?.observations || 0;
    ElMessage.success(moved ? `已保存，并同步更新 ${moved} 条历史数据的指标名` : '已保存');
  } catch (error) {
    ElMessage.error(error.message || '保存失败');
  } finally {
    saving.value = false;
  }
}

/* 分组：主数据化之后是独立实体——能建空组、能改名、能删（仅空组） */
async function saveGroup() {
  const name = form.group.trim();
  if (!name || !itemValid(name)) return;
  saving.value = true;
  try {
    const code = form.code.trim() || undefined;
    const result = form.groupId
      ? await api('data/scope-library/group/update', { id: form.groupId, name, code })
      : await api('data/scope-library/group', { name, code });
    library.value = result.library || [];
    dialogVisible.value = false;
    ElMessage.success(form.groupId ? `分组已改名为「${name}」` : `已创建分组「${name}」`);
  } catch (error) {
    ElMessage.error(error.message || (form.groupId ? '重命名失败' : '创建分组失败'));
  } finally {
    saving.value = false;
  }
}

/* 一级分组：点删除即可删。组内有指标时一并删除（含其历史数据），
   所以确认框要把「删几个指标」说清楚，不做静默连带。 */
async function removeGroup(row) {
  const tip = row.count
    ? `分组「${row.group}」下有 ${row.count} 个指标，删除分组会一并删除这些指标及其历史数据，且不可恢复。确认删除？`
    : `删除空分组「${row.group}」？`;
  try {
    await ElMessageBox.confirm(tip, '删除分组', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    });
  } catch { return; }
  try {
    const result = await api('data/scope-library/group/delete', { id: row.groupId, cascade: true });
    library.value = result.library || [];
    const removed = result.removed_indicators || 0;
    ElMessage.success(removed ? `已删除分组及组内 ${removed} 个指标` : '已删除分组');
  } catch (error) {
    ElMessage.error(error.message || '删除分组失败');
  }
}

async function confirmRemove(message) {
  try {
    await ElMessageBox.confirm(message, '删除指标？', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    });
    return true;
  } catch { return false; }
}

async function removeOne(row) {
  if (!await confirmRemove(`删除指标「${row.name}」？已入库数据的指标不能删除，需要停用时请联系管理员。`)) return;
  await postDelete([row.indicatorId]);
}

async function postDelete(ids) {
  try {
    const result = await api('data/scope-library/delete', { ids });
    library.value = result.library || [];
    ElMessage.success(`已删除 ${result.removed ?? ids.length} 项`);
  } catch (error) {
    ElMessage.error(error.message || '删除失败');
  }
}

onMounted(load);
</script>

<style scoped>

.lib-unclassified { color: #e6a23c; }
/* 一级目录：就是一行字，不加任何标签底色 */
.lib-group-name { font-weight: 600; color: var(--ink-1); }
.lib-code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: #64748b; letter-spacing: 0.02em; }
.lib-warn { color: #e6a23c; }
.lib-newgroup { color: var(--accent); }
/* 表单与树同构：一级在上、二级缩进在下，用一条折线表达从属关系 */
.lib-treeform { display: flex; flex-direction: column; gap: 18px; }
.lib-treeform-node { position: relative; border: 1px solid var(--line); border-radius: var(--radius); padding: 10px 12px; }
/* 一级只是归属说明，不是内容块：不加卡片外观，直接排字 */
.lib-treeform-node.is-parent { border: 0; border-radius: 0; padding: 0; background: none; }
.lib-treeform-node.is-child { margin-left: 24px; background: #fff; }
.lib-treeform-node.is-child::before {
  content: ''; position: absolute; left: -16px; top: -18px; width: 15px; height: 38px;
  border-left: 1px solid #c9d4e2; border-bottom: 1px solid #c9d4e2; border-bottom-left-radius: 7px;
}
.lib-treeform-label { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; font-size: 13px; font-weight: 500; color: #1f2d3d; }
/* 编码行：和名称分开，提示「留空自动生成」 */
.lib-code-row { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
.lib-code-label { flex: none; width: 28px; font-size: 12px; color: #7a8699; }
.lib-code-row :deep(.el-input) { flex: 1; min-width: 0; }
.lib-code-row :deep(.el-input__inner) { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: 0.03em; }
.lib-treeform-node .caption { margin: 8px 0 0; }
</style>
