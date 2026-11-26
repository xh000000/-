<template>
  <div class="viewpoints-page">
    <PageHead title="观点库" description="沉淀研究观点并自动回溯准确率：观点到期后对照指标库价格结算，支撑研究员能力画像。">
      <el-button type="primary" :disabled="!canCreate" @click="openCreate">登记观点</el-button>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </PageHead>

    <div class="entry-summary vp-summary">
      <div><span>整体正确率</span><strong>{{ stats.overall?.accuracy === null || stats.overall?.accuracy === undefined ? '—' : stats.overall.accuracy + '%' }}</strong><p>已结算观点中方向判断正确的占比</p></div>
      <div><span>已结算</span><strong>{{ stats.overall?.settled || 0 }}<small>条</small></strong><p>含无法结算 {{ stats.overall?.unavailable || 0 }} 条</p></div>
      <div><span>在途观察</span><strong>{{ stats.overall?.pending || 0 }}<small>条</small></strong><p>到期后自动对照价格结算</p></div>
      <div><span>判定阈值</span><strong>±{{ stats.threshold ?? 1 }}%</strong><p>区间涨跌幅不超过阈值计「持平」</p></div>
    </div>

    <div class="panel" style="padding: 18px 20px; margin-bottom: 20px">
      <div class="filter-bar" style="padding: 0; margin-bottom: 12px">
        <el-select v-model="filters.commodity" clearable filterable placeholder="全部品种" style="width: 150px">
          <el-option v-for="item in commodityNames" :key="item" :label="item" :value="item" />
        </el-select>
        <el-select v-model="filters.direction" clearable placeholder="全部方向" style="width: 120px">
          <el-option v-for="item in ['看多', '看空', '震荡']" :key="item" :label="item" :value="item" />
        </el-select>
        <el-select v-model="filters.status" clearable placeholder="全部状态" style="width: 120px">
          <el-option label="在途" value="在途" />
          <el-option label="已结算" value="已结算" />
        </el-select>
        <el-select v-model="filters.outcome" clearable placeholder="全部结果" style="width: 120px">
          <el-option v-for="item in ['正确', '错误', '持平', '无法结算']" :key="item" :label="item" :value="item" />
        </el-select>
        <el-input v-model="filters.q" placeholder="搜索观点人 / 依据" clearable style="width: 180px" />
        <el-button link @click="resetFilters">重置</el-button>
      </div>

      <el-table :data="list" size="default" empty-text="还没有观点记录，点右上角「登记观点」开始沉淀">
        <el-table-column label="品种 / 方向" width="128">
          <template #default="{ row }">
            <b>{{ row.commodity }}</b>
            <el-tag :type="directionType(row.direction)" size="small" style="margin-left: 6px" disable-transitions>
              {{ row.direction }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="观点人" width="84" show-overflow-tooltip prop="user_name" />
        <el-table-column label="依据" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.basis || '—' }}</template>
        </el-table-column>
        <el-table-column label="基准价" width="128">
          <template #default="{ row }">
            {{ formatPrice(row.benchmark_price) }}
            <span class="tiny hint">{{ row.benchmark_date }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结算价" width="128">
          <template #default="{ row }">
            <template v-if="row.result_price !== null && row.result_price !== undefined">
              {{ formatPrice(row.result_price) }}
              <span class="tiny hint">{{ row.result_date }}</span>
            </template>
            <span v-else class="hint">待结算</span>
          </template>
        </el-table-column>
        <el-table-column label="涨跌幅" width="92" align="right">
          <template #default="{ row }">
            <span v-if="row.change_pct !== null && row.change_pct !== undefined"
                  :style="{ color: row.change_pct > 0 ? '#d25252' : row.change_pct < 0 ? '#3fb27f' : '#64748b', fontWeight: 600 }">
              {{ row.change_pct > 0 ? '+' : '' }}{{ row.change_pct }}%
            </span>
            <span v-else class="hint">—</span>
          </template>
        </el-table-column>
        <el-table-column label="结果" width="96" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.outcome" :type="outcomeType(row.outcome)" size="small" disable-transitions>
              {{ row.outcome }}
            </el-tag>
            <span v-else class="hint">—</span>
          </template>
        </el-table-column>
        <el-table-column label="到期日" width="104">
          <template #default="{ row }">{{ row.expire_date }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <div class="cell-actions">
              <el-button v-if="row.status === '在途' && (row.user_id === user.id || user.role === 'admin')"
                         link type="primary" size="small" @click="settleNow(row)">结算</el-button>
              <el-button v-if="row.user_id === user.id || user.role === 'admin'"
                         link type="danger" size="small" @click="remove(row)">删除</el-button>
              <span v-if="!(row.user_id === user.id || user.role === 'admin')" class="hint">—</span>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="vp-portraits">
      <div class="panel vp-portrait">
        <div class="panel-header"><h3>研究员画像</h3><p class="caption">按观点人统计正确率与方向分布（仅已结算观点）</p></div>
        <el-table :data="portraitRows(stats.by_user)" size="small" empty-text="暂无已结算观点">
          <el-table-column label="观点人" prop="name" min-width="90" />
          <el-table-column label="已结算" prop="total" width="76" align="center" />
          <el-table-column label="正确率" width="90" align="center">
            <template #default="{ row }">{{ row.accuracy === null ? '—' : row.accuracy + '%' }}</template>
          </el-table-column>
          <el-table-column label="方向分布" min-width="150">
            <template #default="{ row }">
              <span class="tiny">看多 {{ row['看多'] || 0 }} · 看空 {{ row['看空'] || 0 }} · 震荡 {{ row['震荡'] || 0 }}</span>
            </template>
          </el-table-column>
          <el-table-column label="正确 / 错误 / 持平" width="150" align="center">
            <template #default="{ row }">
              <span class="tiny">{{ row['正确'] }} / {{ row['错误'] }} / {{ row['持平'] }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="panel vp-portrait">
        <div class="panel-header"><h3>品种正确率</h3><p class="caption">哪个品种上大家的观点更靠谱</p></div>
        <el-table :data="portraitRows(stats.by_commodity)" size="small" empty-text="暂无已结算观点">
          <el-table-column label="品种" prop="name" min-width="90" />
          <el-table-column label="已结算" prop="total" width="76" align="center" />
          <el-table-column label="正确率" width="90" align="center">
            <template #default="{ row }">{{ row.accuracy === null ? '—' : row.accuracy + '%' }}</template>
          </el-table-column>
          <el-table-column label="正确 / 错误 / 持平" width="150" align="center">
            <template #default="{ row }">
              <span class="tiny">{{ row['正确'] }} / {{ row['错误'] }} / {{ row['持平'] }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-dialog v-model="createVisible" title="登记观点" width="520px" @closed="resetCreate">
      <el-form label-width="88px" label-position="left">
        <el-form-item label="品种" required>
          <el-select v-model="createForm.commodity" filterable placeholder="选择品种" style="width: 100%">
            <el-option v-for="item in commodityNames" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="方向" required>
          <el-radio-group v-model="createForm.direction">
            <el-radio-button value="看多">看多</el-radio-button>
            <el-radio-button value="看空">看空</el-radio-button>
            <el-radio-button value="震荡">震荡</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="观察期">
          <el-select v-model="createForm.horizon_days" style="width: 100%">
            <el-option v-for="item in [3, 5, 10, 20, 30, 60, 90]" :key="item" :label="item + ' 个自然日'" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="基准价">
          <el-input v-model="createForm.benchmark_price" placeholder="留空则自动取指标库最新价">
            <template #append>元</template>
          </el-input>
          <p class="tiny hint" style="margin-top: 4px">
            自动取价优先级：现货价 → 收盘价 → 结算价 → 最新点位；到期结算用同一指标对照
          </p>
        </el-form-item>
        <el-form-item label="观点依据">
          <el-input v-model="createForm.basis" type="textarea" :rows="4" maxlength="1000" show-word-limit
                    placeholder="为什么看这个方向？核心逻辑与数据依据（会进入画像追溯）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">登记</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import PageHead from '../components/PageHead.vue';
import { api } from '../api';
import { commodities, user } from '../store/session';

const items = ref([]);
const stats = ref({});
const loading = ref(false);
const createVisible = ref(false);
const saving = ref(false);
const filters = reactive({ commodity: '', direction: '', status: '', outcome: '', q: '' });
const createForm = reactive({ commodity: '', direction: '看多', horizon_days: 5, basis: '', benchmark_price: '' });

const canCreate = computed(() => ['admin', 'researcher'].includes(user.value.role));
const commodityNames = computed(() =>
  commodities.value.filter(item => item.code && item.enabled !== 0).map(item => item.name)
);

const list = computed(() => items.value.filter(row => {
  const keyword = filters.q.trim().toLowerCase();
  return (!filters.commodity || row.commodity === filters.commodity)
    && (!filters.direction || row.direction === filters.direction)
    && (!filters.status || row.status === filters.status)
    && (!filters.outcome || row.outcome === filters.outcome)
    && `${row.user_name} ${row.basis || ''}`.toLowerCase().includes(keyword);
}));

function portraitRows(by) {
  return Object.entries(by || {}).map(([name, row]) => ({ name, ...row }));
}

function directionType(direction) {
  return { 看多: 'danger', 看空: 'success', 震荡: 'info' }[direction] || 'info';
}

function outcomeType(outcome) {
  return { 正确: 'success', 错误: 'danger', 持平: 'info', 无法结算: 'warning' }[outcome] || 'info';
}

function formatPrice(value) {
  if (value === null || value === undefined) return '—';
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function resetFilters() {
  Object.assign(filters, { commodity: '', direction: '', status: '', outcome: '', q: '' });
}

function openCreate() {
  createVisible.value = true;
}

function resetCreate() {
  Object.assign(createForm, { commodity: '', direction: '看多', horizon_days: 5, basis: '', benchmark_price: '' });
}

async function load() {
  loading.value = true;
  try {
    const [listRes, statsRes] = await Promise.all([api('viewpoints'), api('viewpoints/stats')]);
    items.value = listRes.items || [];
    stats.value = statsRes;
  } catch (error) {
    ElMessage.error(error.message || '读取观点库失败');
  } finally {
    loading.value = false;
  }
}

async function save() {
  if (!createForm.commodity) return ElMessage.warning('请选择品种');
  if (!createForm.basis.trim()) return ElMessage.warning('请填写观点依据，便于日后追溯');
  saving.value = true;
  try {
    await api('viewpoints', {
      commodity: createForm.commodity,
      direction: createForm.direction,
      horizon_days: createForm.horizon_days,
      basis: createForm.basis.trim(),
      benchmark_price: createForm.benchmark_price === '' ? null : createForm.benchmark_price,
    });
    ElMessage.success('观点已登记，到期后自动对照价格结算');
    createVisible.value = false;
    load();
  } catch (error) {
    ElMessage.error(error.message || '登记失败');
  } finally {
    saving.value = false;
  }
}

async function settleNow(row) {
  try {
    await ElMessageBox.confirm(
      `提前结算「${row.commodity} · ${row.direction}」？将用指标库最新可得价格对照基准价判定结果，此后不可修改。`,
      '提前结算', { type: 'warning' });
  } catch {
    return;
  }
  try {
    await api('viewpoints/settle', { id: row.id });
    ElMessage.success('已结算');
    load();
  } catch (error) {
    ElMessage.error(error.message || '结算失败');
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`删除「${row.commodity} · ${row.direction}」这条观点？删除后不可恢复。`,
      '删除观点', { type: 'warning' });
  } catch {
    return;
  }
  try {
    await api('viewpoints/delete', { id: row.id });
    ElMessage.success('已删除');
    load();
  } catch (error) {
    ElMessage.error(error.message || '删除失败');
  }
}

onMounted(load);
</script>

<style scoped>
.vp-summary strong { font-size: 26px; }
.vp-portraits { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.vp-portrait { padding: 18px 20px; }
.panel-header h3 { margin: 0 0 4px; font-size: 15px; }
@media (max-width: 1100px) { .vp-portraits { grid-template-columns: minmax(0, 1fr); } }
</style>
