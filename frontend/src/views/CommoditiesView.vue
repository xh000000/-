<template>
  <div>
    <PageContainer title="品种管理">
      <div class="panel">
        <div class="panel-toolbar">
          <el-button type="primary" @click="openDialog(null)">添加品种</el-button>
        </div>
        <el-table
          ref="tableRef"
          :data="tree" row-key="id" :tree-props="{ children: 'children' }" empty-text="暂无品种" border
          @header-dragend="onHeaderDragend"
        >
          <el-table-column label="品种 / 板块" min-width="240">
            <template #default="{ row }">
              <span :class="{ 'commodity-group-name': row.depth === 1 }">{{ row.name }}</span>
              <span v-if="row.children?.length" class="caption" style="margin-left: 8px">{{ row.children.length }} 个品种</span>
            </template>
          </el-table-column>
          <el-table-column label="合约代码" width="140">
            <template #default="{ row }">
              <code v-if="row.code" class="commodity-code">{{ row.code }}</code>
              <span v-else class="caption">—</span>
            </template>
          </el-table-column>
          <el-table-column label="交易所" width="112">
            <template #default="{ row }">
              <span v-if="row.exchange">{{ exchangeName(row.exchange) }}</span>
              <span v-else class="caption">—</span>
            </template>
          </el-table-column>
          <el-table-column label="别名" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.aliases?.length" class="caption">{{ row.aliases.join('、') }}</span>
              <span v-else class="caption">—</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="96">
            <template #default="{ row }">
              <el-tag :type="row.effective_enabled ? 'success' : 'info'" size="small" disable-transitions>
                {{ row.effective_enabled ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="130" align="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
              <el-button link type="danger" size="small" :loading="removing === row.id" @click="remove(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </PageContainer>

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
        <el-form-item label="合约代码" :required="Boolean(form.parent_id)">
          <el-input
            v-model="form.code" maxlength="40" :disabled="!form.parent_id"
            :placeholder="form.parent_id ? '如 CU、I、IF/IH/IC/IM，品种内唯一' : '先选择上级板块'"
            @input="form.code = form.code.toUpperCase()"
          />
        </el-form-item>
        <el-form-item label="交易所">
          <el-select v-model="form.exchange" clearable :disabled="!form.parent_id" placeholder="选择交易所" style="width: 100%">
            <el-option v-for="item in exchangeOptions" :key="item.value" :label="`${item.label} · ${item.value}`" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="别名">
          <el-input
            v-model="form.aliasesText" :disabled="!form.parent_id" maxlength="200"
            placeholder="逗号分隔，如 沪铜，电解铜；用于指标名自动识别品种"
          />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <p class="caption">品种仅支持两级：板块 → 品种。合约代码是品种的唯一标识，保存时全局查重，重复会直接提示；别名供录入数据时按名称自动归品种。</p>
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
import PageContainer from '../components/PageContainer.vue';
import { api } from '../api';
import { createResizeHandler } from '../utils/tableResize';
import { commodities, refresh } from '../store/session';

const tableRef = ref(null);
/* 列宽拖拽：被拖列保留宽度，另选一列吸收剩余宽度（避免右侧留白又不弹回原宽） */
const onHeaderDragend = createResizeHandler(tableRef);

const busy = ref(false);
const removing = ref(null);
const visible = ref(false);
const form = reactive({ id: null, name: '', code: '', exchange: '', aliasesText: '', parent_id: null, enabled: true });

/* 交易所短码与中文名：库里存短码，界面显示中文，避免同一家交易所两种写法 */
const exchangeOptions = [
  { value: 'SHFE', label: '上期所' },
  { value: 'INE', label: '上期能源' },
  { value: 'DCE', label: '大商所' },
  { value: 'CZCE', label: '郑商所' },
  { value: 'GFEX', label: '广期所' },
  { value: 'CFFEX', label: '中金所' },
];
const EXCHANGE_NAMES = Object.fromEntries(exchangeOptions.map(item => [item.value, item.label]));
const exchangeName = code => EXCHANGE_NAMES[code] || code;

/* 别名在库里是 JSON 数组，兼容早期逗号分隔写法 */
function parseAliases(raw) {
  if (Array.isArray(raw)) return raw.filter(Boolean);
  const text = String(raw || '').trim();
  if (!text) return [];
  if (text.startsWith('[')) {
    try {
      const data = JSON.parse(text);
      return Array.isArray(data) ? data.filter(Boolean) : [];
    } catch { return []; }
  }
  return text.split(/[,，]/).map(item => item.trim()).filter(Boolean);
}

const source = computed(() =>
  commodities.value.map(item => ({
    ...item,
    enabled: Boolean(item.enabled),
    parent_id: item.parent_id || null,
    exchange: item.exchange || '',
    aliases: parseAliases(item.aliases),
    position: item.position || 0,
  }))
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
    list.sort((a, b) => (a.position - b.position) || (a.id - b.id));
    list.forEach(item => {
      item.children.sort((a, b) => (a.position - b.position) || (a.id - b.id));
      item.effective_enabled = item.enabled && !(item.parent_id && !map.get(item.parent_id).enabled);
      finalize(item.children);
    });
  };
  finalize(roots);
  return roots;
});

/* 上级板块候选：任意一级板块（不必为空，可以继续往里加品种），排除自身；
   有子品种的一级不能自己变成二级，这个由后端把关并给出提示。 */
const parentOptions = computed(() =>
  source.value.filter(item => !item.parent_id && item.id !== form.id)
);

const hasChildren = id => source.value.some(item => item.parent_id === id);

function openDialog(row, parentId = null) {
  form.id = row?.id ?? null;
  form.name = row?.name || '';
  form.code = row?.code || '';
  form.exchange = row?.exchange || '';
  form.aliasesText = (row?.aliases || []).join('，');
  /* 编辑：取自身上级；新增：板块行的「添加品种」预选该板块为上级 */
  form.parent_id = row ? (row.parent_id ?? null) : parentId;
  form.enabled = row ? Boolean(row.enabled) : true;
  visible.value = true;
}

function reset() {
  form.id = null;
  form.name = '';
  form.code = '';
  form.exchange = '';
  form.aliasesText = '';
  form.parent_id = null;
  form.enabled = true;
}

async function save() {
  const name = form.name.trim();
  if (!name) return ElMessage.warning('请填写品种名称');
  /* 品种以合约代码唯一标识；板块不占编码 */
  if (form.parent_id && !form.code.trim()) return ElMessage.warning('请填写合约代码：品种以合约代码作为唯一标识');
  busy.value = true;
  try {
    await api('catalog', {
      kind: 'commodities',
      id: form.id,
      name,
      code: form.code.trim().toUpperCase(),
      exchange: form.exchange || '',
      aliases: form.aliasesText.split(/[,，\s]+/).map(item => item.trim()).filter(Boolean),
      parent_id: form.parent_id || null,
      enabled: form.enabled,
    });
    await refresh();
    visible.value = false;
    ElMessage.success('品种已保存');
  } catch (error) {
    /* 后端的校验文案已是一整句，去掉统一的「输入无效：」前缀更好读 */
    ElMessage.error(String(error.message || '保存失败').replace(/^输入无效：/, ''));
  } finally {
    busy.value = false;
  }
}

/* 删除只对空板块成立：有子品种、或被报告章节引用的品种，后端会拒绝并说明原因 */
async function remove(row) {
  const hint = row.depth === 1 && row.children?.length
    ? `「${row.name}」下还有 ${row.children.length} 个品种，需要先删掉或移出子品种。`
    : `删除后不影响已入库的行情数据，但章节里对「${row.name}」的关联会失效。`;
  try {
    await ElMessageBox.confirm(hint, `删除品种「${row.name}」？`, {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    });
  } catch { return; }
  removing.value = row.id;
  try {
    await api('catalog', { kind: 'commodities', action: 'delete', id: row.id });
    await refresh();
    ElMessage.success(`已删除「${row.name}」`);
  } catch (error) {
    ElMessage.error(error.message || '删除失败');
  } finally {
    removing.value = null;
  }
}
</script>

<style scoped>
:deep(.el-table) { --el-table-border-color: #eef2f7; }
/* 板块行：不加标签框，只用加粗文字区分 */
.commodity-group-name { font-weight: 600; color: #183153; }
</style>
