<template>
  <div class="viewpoints-page">
    <PageContainer title="研报观点跟踪">
      <template #actions>
        <el-button v-if="user.role === 'admin'" text @click="rulesVisible = true">复盘规则</el-button>
      </template>
    <div v-show="activeTab === 'candidates'" class="vp-toolbar">
      <div class="vp-date-field"><span>发布日期</span><el-date-picker v-model="publicationRange" type="daterange" value-format="YYYY-MM-DD" range-separator="—" start-placeholder="开始日期" end-placeholder="结束日期" :clearable="false" :disabled="extracting || loading || aiRunning" @change="load" /></div>
      <div class="vp-extract-actions"><el-select v-model="extractionMethod" aria-label="提取方式" :disabled="extracting || aiRunning" style="width:120px"><el-option label="规则提取" value="rule" /><el-option label="AI 提取" value="ai" /></el-select><el-button type="primary" :loading="extracting || aiRunning" :disabled="loading || !publicationRange?.length" @click="extractByDate">提取研报观点</el-button></div>
    </div>
    <div v-if="aiJob" class="vp-ai-task"><span>AI 提取 · {{ aiJob.status }} · {{ aiJob.result?.completed || 0 }}/{{ aiJob.result?.total || 0 }} 篇 · 新增 {{ aiJob.result?.added || 0 }} 条</span><span v-if="aiJob.error" class="vp-due">{{ aiJob.error }}</span></div>
    <div class="vp-summary">
      <div><span>待确认</span><strong>{{ pendingCandidates.length }}</strong></div>
      <div><span>跟踪中</span><strong>{{ stats.overall?.pending || 0 }}</strong></div>
      <div><span>已结算</span><strong>{{ stats.overall?.settled || 0 }}</strong></div>
      <div><span>复盘正确率</span><strong>{{ stats.overall?.accuracy === null || stats.overall?.accuracy === undefined ? '—' : stats.overall.accuracy + '%' }}</strong></div>
    </div>

    <el-tabs v-model="activeTab" class="vp-tabs"><el-tab-pane :label="`待确认（${pendingCandidates.length}）`" name="candidates" /><el-tab-pane label="跟踪中" name="records" /><el-tab-pane label="复盘结果" name="results" /></el-tabs>
    <el-alert v-if="loadError" type="error" :title="loadError" :closable="false" show-icon style="margin-bottom:12px" />
    <div v-show="activeTab === 'candidates'" class="panel vp-records">
      <div class="vp-list-heading"><div><h3>候选观点</h3></div><div><el-checkbox v-model="showIgnored">显示已忽略</el-checkbox><el-button v-if="selectedCandidates.length" type="primary" plain @click="openConfirm(selectedCandidates)">批量确认<span v-if="selectedCandidates.length">（{{ selectedCandidates.length }}）</span></el-button></div></div>
      <el-table v-loading="loading" :data="visibleCandidates" empty-text="暂无候选观点" @selection-change="selectedCandidates = $event">
        <el-table-column type="selection" width="48" :selectable="row => row.can_confirm && row.status === '待确认'" />
        <el-table-column label="来源研报" min-width="190"><template #default="{ row }"><el-button link type="primary" @click="openReport(row.report_id)">{{ row.report_title }}</el-button><el-tag v-if="row.source_method === 'ai'" size="small" effect="plain">AI</el-tag><p class="tiny hint">{{ row.author_name }} · {{ row.published_date }}</p></template></el-table-column>
        <el-table-column label="品种 / 方向" width="140"><template #default="{ row }"><b>{{ row.commodity }}</b><p class="tiny">{{ row.direction || '方向待核对' }} · {{ row.horizon_days ? row.horizon_days + ' 天' : '期限待确认' }}</p></template></el-table-column>
        <el-table-column label="研报原文" min-width="280"><template #default="{ row }"><p class="vp-excerpt">{{ row.excerpt }}</p><span class="caption">{{ row.reason }}</span></template></el-table-column>
        <el-table-column label="操作" width="140" fixed="right"><template #default="{ row }"><template v-if="row.status === '待确认' && row.can_confirm"><el-button link type="primary" @click="openConfirm([row])">编辑确认</el-button><el-button link :disabled="processing" @click="ignoreCandidate(row)">忽略</el-button></template><span v-else class="caption">{{ row.status === '已忽略' ? '已忽略' : '待作者或管理员确认' }}</span></template></el-table-column>
      </el-table>
    </div>
    <div v-show="activeTab !== 'candidates'" class="panel vp-records">
      <div class="vp-list-heading"><h3>{{ activeTab === 'results' ? '复盘结果' : '跟踪中的观点' }} <span class="caption">{{ list.length }} 条</span></h3><el-radio-group v-model="scope" size="small"><el-radio-button value="all">全部观点</el-radio-button><el-radio-button value="mine">我的观点</el-radio-button><el-radio-button v-if="activeTab === 'records'" value="due">到期待结算</el-radio-button></el-radio-group></div>
      <div class="filter-bar vp-filters">
        <el-select v-model="filters.commodity" clearable filterable placeholder="全部品种" style="width: 150px">
          <el-option v-for="item in commodityNames" :key="item" :label="item" :value="item" />
        </el-select>
        <el-select v-model="filters.direction" clearable placeholder="全部方向" style="width: 120px">
          <el-option v-for="item in ['看多', '看空', '震荡']" :key="item" :label="item" :value="item" />
        </el-select>
        <el-select v-if="activeTab === 'results'" v-model="filters.outcome" clearable placeholder="全部结果" style="width: 120px">
          <el-option v-for="item in ['正确', '错误', '持平', '无法结算']" :key="item" :label="item" :value="item" />
        </el-select>
        <el-input v-model="filters.q" placeholder="搜索品种 / 观点人 / 依据" aria-label="搜索观点" clearable style="width: 180px" />
        <el-button link @click="resetFilters">重置</el-button>
      </div>

      <el-alert v-if="loadError" type="error" :title="loadError" :closable="false" show-icon style="margin-bottom:12px" />
      <el-table v-loading="loading" :data="pagedList" size="default" :empty-text="items.length ? '没有符合筛选条件的观点，请调整筛选' : '暂无跟踪记录，请先确认研报候选观点'">
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
            <span v-else class="hint">{{ row.status === '在途' ? '待结算' : '无可用价格' }}</span>
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
          <template #default="{ row }"><span>{{ row.expire_date }}</span><p class="tiny" :class="{ 'vp-due': isDue(row), hint: !isDue(row) }">{{ observationLabel(row) }}</p></template>
        </el-table-column>
        <el-table-column label="操作" width="165" fixed="right">
          <template #default="{ row }">
            <div class="cell-actions">
              <el-button link type="primary" size="small" @click="showDetail(row)">详情</el-button>
              <el-button v-if="!row.report_id && row.status === '在途' && (row.user_id === user.id || user.role === 'admin')"
                         link type="primary" size="small" @click="settleNow(row)">结算</el-button>
              <el-button v-if="!row.report_id && (row.user_id === user.id || user.role === 'admin')"
                         link type="danger" size="small" @click="remove(row)">删除</el-button>
              <span v-if="!(row.user_id === user.id || user.role === 'admin')" class="hint">—</span>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination v-if="list.length" v-model:current-page="page" v-model:page-size="pageSize" :page-sizes="[10, 20, 50]" :total="list.length" layout="total, sizes, prev, pager, next" class="vp-pagination" />
    </div>

    <div v-show="activeTab === 'results'" class="vp-portraits"><p class="vp-stat-note">统计口径：按每条观点确认时锁定的阈值判定；正确率为正确数 / 有效结算数（含持平），无法结算不计入。以下汇总覆盖全部可见观点，不受列表筛选影响。</p>
      <div class="panel vp-portrait">
        <div class="panel-header"><h3>研究员复盘统计</h3></div>
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
        <div class="panel-header"><h3>品种正确率</h3></div>
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

    <el-drawer v-model="detailVisible" title="观点详情" size="min(620px, 100vw)">
      <template v-if="detail">
        <el-alert v-if="detail.report_id" title="来源：已发布研报定稿，价格来自指标库" type="info" :closable="false" />
        <p v-if="detail.report_id"><el-button link type="primary" @click="openReport(detail.report_id)">{{ detail.report_title }} · {{ detail.published_date }}</el-button></p>
        <p class="caption">本条复盘阈值：±{{ detail.evaluation_threshold || 1 }}%（确认后锁定）</p>
        <div class="vp-detail-title"><h2>{{ detail.commodity }}</h2><el-tag :type="directionType(detail.direction)">{{ detail.direction }}</el-tag><el-tag :type="outcomeType(detail.outcome)">{{ detail.outcome || detail.status }}</el-tag></div>
        <el-descriptions :column="2" border>
          <el-descriptions-item v-if="detail.candidate_id" label="确认人">{{ candidates.find(c => c.id === detail.candidate_id)?.confirmed_by || '—' }}</el-descriptions-item>
          <el-descriptions-item v-if="detail.candidate_id" label="确认时间">{{ candidates.find(c => c.id === detail.candidate_id)?.confirmed_at || '—' }}</el-descriptions-item>
          <el-descriptions-item label="观点人">{{ detail.user_name }}</el-descriptions-item><el-descriptions-item label="登记时间">{{ detail.created_at || '—' }}</el-descriptions-item>
          <el-descriptions-item label="基准价">{{ formatPrice(detail.benchmark_price) }}</el-descriptions-item><el-descriptions-item label="基准日期">{{ detail.benchmark_date || '—' }}</el-descriptions-item>
          <el-descriptions-item label="观察期">{{ detail.horizon_days }} 个自然日</el-descriptions-item><el-descriptions-item label="到期日">{{ detail.expire_date }}</el-descriptions-item>
          <el-descriptions-item label="结算价">{{ formatPrice(detail.result_price) }}</el-descriptions-item><el-descriptions-item label="结算日期">{{ detail.result_date || '—' }}</el-descriptions-item>
          <el-descriptions-item label="基准来源">{{ detail.benchmark_source || '旧记录未锁定' }}</el-descriptions-item>
          <el-descriptions-item label="取价方式">{{ detail.benchmark_manual ? '手工基准价' : detail.benchmark_source ? '指标库自动取价' : '旧记录未标识' }}</el-descriptions-item>
          <el-descriptions-item label="基准指标" :span="2">{{ detail.benchmark_indicator || '未关联' }}</el-descriptions-item>
          <el-descriptions-item label="价格单位">{{ detail.benchmark_unit || '未标注' }}</el-descriptions-item><el-descriptions-item label="结算来源">{{ detail.result_source || '—' }}</el-descriptions-item>
          <el-descriptions-item label="结算指标" :span="2">{{ detail.result_indicator || '—' }}</el-descriptions-item>
        </el-descriptions>
        <h3 class="vp-detail-heading">观点依据</h3><p class="vp-basis">{{ detail.basis || '—' }}</p><details v-if="detail.source_excerpt" class="vp-original"><summary>研报原文</summary><p class="vp-basis">{{ detail.source_excerpt }}</p></details>
        <el-alert v-if="detail.note" :title="detail.note" type="info" :closable="false" />
      </template>
    </el-drawer>
    <el-dialog v-model="confirmVisible" title="确认研报观点" width="min(760px, 94vw)" :close-on-click-modal="false" :show-close="!saving" :close-on-press-escape="!saving">

      <div v-for="item in confirmation" :key="item.id" class="vp-confirm-item">
        <b>{{ item.commodity }} · {{ item.report_title }}</b><details class="vp-original"><summary>研报原文</summary><p class="vp-basis">{{ item.excerpt }}</p></details>
        <el-form label-width="80px"><el-form-item label="观点说明"><el-input v-model="item.basis" type="textarea" :rows="3" maxlength="3000" show-word-limit /></el-form-item><el-form-item label="判断方向"><el-radio-group v-model="item.direction"><el-radio-button v-for="name in ['看多','看空','震荡']" :key="name" :value="name">{{ name }}</el-radio-button></el-radio-group></el-form-item>
          <el-form-item label="观察期"><el-input-number v-model="item.horizon_days" :min="1" :max="90" /><span class="caption"> 自然日，从 {{ item.published_date }} 起算</span></el-form-item>
        </el-form>
        <p class="caption">{{ matchingRule(item) ? '复盘阈值：±' + matchingRule(item).threshold + '%' : '尚未配置此品种和观察期的复盘规则，请联系管理员' }}</p>
        <el-checkbox v-if="item.conditional" v-model="item.condition_confirmed">已核实原文适用条件，确认可纳入本次复盘</el-checkbox>
      </div>
      <el-checkbox v-model="reviewed">已逐条核对来源原文、方向及观察期</el-checkbox>
      <template #footer><el-button :disabled="saving" @click="confirmVisible = false">取消</el-button><el-button type="primary" :loading="saving" :disabled="!reviewed" @click="confirmSelected">确认并开始跟踪</el-button></template>
    </el-dialog>
    <el-dialog v-model="rulesVisible" title="复盘规则" width="min(740px, 94vw)" :close-on-click-modal="false">
      <div v-for="(rule,index) in ruleDraft.items" :key="index" class="vp-rule-row">
        <el-select v-model="rule.commodity" filterable placeholder="品种"><el-option v-for="name in commodityNames" :key="name" :label="name" :value="name" /></el-select>
        <el-input-number v-model="rule.horizon_days" :min="1" :max="90" aria-label="观察期天数" /><span>天</span>
        <el-input-number v-model="rule.threshold" :min="0.01" :max="100" :precision="2" aria-label="涨跌阈值" /><span>%</span>
        <el-button link type="danger" @click="ruleDraft.items.splice(index,1)">移除</el-button>
      </div>
      <el-button @click="ruleDraft.items.push({commodity:'',horizon_days:5,threshold:1})">添加规则</el-button>
      <template #footer><el-button :disabled="saving" @click="rulesVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveRules">保存规则</el-button></template>
    </el-dialog>
    </PageContainer>
  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import PageContainer from '../components/PageContainer.vue';
import { api } from '../api';
import { useRouter } from 'vue-router';
import { commodities, user } from '../store/session';

const router = useRouter();
const activeTab = ref('candidates');
const dateText=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
const endDay=new Date(),startDay=new Date();startDay.setDate(startDay.getDate()-29);
const publicationRange=ref([dateText(startDay),dateText(endDay)]);
const extracting=ref(false),extractionMethod=ref('rule'),aiJob=ref(null);
const aiRunning=computed(()=>['排队中','运行中'].includes(aiJob.value?.status));
let aiTimer,disposed=false;
async function refreshAIJob(){
 const previous=aiRunning.value;
 try{const result=await api('viewpoints/extraction-job');if(disposed)return;aiJob.value=result.job || null;
 if(previous && !aiRunning.value)await load();
 }catch(e){if(!disposed)loadError.value=e.message;}
 finally{clearTimeout(aiTimer);if(!disposed && aiRunning.value)aiTimer=setTimeout(refreshAIJob,2500);}
}
onBeforeUnmount(()=>{disposed=true;clearTimeout(aiTimer);});
async function extractByDate(){
 if(extracting.value || loading.value || aiRunning.value)return;
 if(publicationRange.value?.length!==2)return ElMessage.warning('请选择完整的发布日期范围');
 extracting.value=true;
 try{const result=await api('viewpoints/extract',{start_date:publicationRange.value[0],end_date:publicationRange.value[1],...(extractionMethod.value==='ai' ? {method:'ai'} : {})});
 if(result.task_id){await refreshAIJob();activeTab.value='candidates';}
 else{await load();activeTab.value='candidates';ElMessage.success(result.added ? `提取完成，新增 ${result.added} 条候选观点` : '没有新增观点');}}
 catch(error){ElMessage.error(error.message || '观点提取失败');}finally{extracting.value=false;}
}
const candidates = ref([]);
const selectedCandidates = ref([]);
const showIgnored = ref(false);
const pendingCandidates = computed(() => candidates.value.filter(x => x.status === '待确认'));
const visibleCandidates = computed(() => candidates.value.filter(x => x.status === '待确认' || (showIgnored.value && x.status === '已忽略')));
const confirmVisible = ref(false);
const rulesVisible = ref(false);
const processing = ref(false);
const confirmation = ref([]);
const reviewed = ref(false);
const ruleDraft = reactive({ revision:0, items:[] });
const ruleSet = ref([]);
watch(rulesVisible, visible => { if (!visible) ruleDraft.items = JSON.parse(JSON.stringify(ruleSet.value)); });
function matchingRule(item) { return ruleSet.value.find(r => r.commodity === item.commodity && r.horizon_days === item.horizon_days); }
function openReport(id) { router.push({ name: 'editor', params: { id }, query: { mode: 'view' } }); }
function openConfirm(rows) { confirmation.value = rows.map(row => ({...row, basis:row.draft_basis || row.excerpt, horizon_days: row.horizon_days || undefined, condition_confirmed:false})); reviewed.value = false; confirmVisible.value = true; }
async function confirmSelected() {
  if (saving.value || !reviewed.value) return;
  saving.value = true;
  try {
    await api('viewpoints/confirm', {items: confirmation.value.map(x => ({id:x.id,basis:x.basis,direction:x.direction,horizon_days:x.horizon_days,reviewed:true,condition_confirmed:x.condition_confirmed}))});
    confirmVisible.value = false; await load(); activeTab.value = 'records'; ElMessage.success('已确认，系统已绑定价格序列；到期观点已自动复盘');
  } catch(error) { ElMessage.error(error.message || '确认失败'); }
  finally { saving.value = false; }
}
async function ignoreCandidate(row) {
  if(processing.value) return;
  try { await ElMessageBox.confirm('忽略这条候选观点？将保留忽略记录，重复提取不会再次生成。','忽略候选'); } catch { return; }
  processing.value = true;
  try { await api('viewpoints/ignore',{id:row.id}); await load(); } catch(error) { ElMessage.error(error.message); } finally { processing.value = false; }
}
async function saveRules() {
  if(saving.value) return;
  saving.value = true;
  try { await api('viewpoints/rules',ruleDraft); rulesVisible.value = false; await load(); ElMessage.success('复盘规则已保存'); }
  catch(error) { ElMessage.error(error.message || '保存失败'); } finally { saving.value = false; }
}
const scope = ref('all');
const page = ref(1);
const pageSize = ref(10);
const loadError = ref('');
const detailVisible = ref(false);
const detailId = ref(null);
const detail = computed(() => items.value.find(row => row.id === detailId.value));
function showDetail(row) { detailId.value = row.id; detailVisible.value = true; }
function today() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; }
function isDue(row) { return row.status === '在途' && row.expire_date && row.expire_date <= today(); }
function observationLabel(row) { return row.status !== '在途' ? '已结算' : isDue(row) ? '已到期 · 待结算' : `观察中 · ${row.horizon_days} 天`; }
const items = ref([]);
const stats = ref({});
const loading = ref(false);
const saving = ref(false);
const filters = reactive({ commodity: '', direction: '', status: '', outcome: '', q: '' });



const commodityNames = computed(() =>
  commodities.value.filter(item => item.code && item.enabled !== 0).map(item => item.name)
);

const list = computed(() => items.value.filter(row => {
  const keyword = filters.q.trim().toLowerCase();
  return (activeTab.value !== 'records' || row.status === '在途')
    && (activeTab.value !== 'results' || row.status === '已结算')
    && (scope.value !== 'mine' || row.user_id === user.value.id)
    && (scope.value !== 'due' || isDue(row))
    && (!filters.commodity || row.commodity === filters.commodity)
    && (!filters.direction || row.direction === filters.direction)
    && (activeTab.value !== 'results' || !filters.outcome || row.outcome === filters.outcome)
    && `${row.commodity} ${row.user_name} ${row.basis || ''}`.toLowerCase().includes(keyword);
}));

const pagedList = computed(() => list.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value));
watch(activeTab,value=>{if(value!=='records' && scope.value==='due')scope.value='all';});
watch([() => ({ ...filters }), scope, pageSize, activeTab], () => { page.value = 1; });
watch(() => list.value.length, length => { page.value = Math.min(page.value, Math.max(1, Math.ceil(length / pageSize.value))); });

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
  scope.value = 'all';
  Object.assign(filters, { commodity: '', direction: '', status: '', outcome: '', q: '' });
}

async function load() {
  loading.value = true;
  loadError.value = '';
  try {
    const [listRes, statsRes, candidateRes, rulesRes] = await Promise.all([api('viewpoints'), api('viewpoints/stats'), api('viewpoints/candidates'+(publicationRange.value?.length===2 ? `?start_date=${publicationRange.value[0]}&end_date=${publicationRange.value[1]}` : '')), api('viewpoints/rules')]);
    items.value = listRes.items || [];
    stats.value = statsRes;
    candidates.value = candidateRes.items || []; selectedCandidates.value = [];
    ruleSet.value = rulesRes.items || []; ruleDraft.revision = rulesRes.revision || 0; ruleDraft.items = JSON.parse(JSON.stringify(ruleSet.value));
  } catch (error) {
    loadError.value = error.message || '读取观点库失败';
    ElMessage.error(loadError.value);
  } finally {
    loading.value = false;
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

onMounted(()=>{load();refreshAIJob();});
</script>

<style scoped>
.vp-excerpt { margin:0 0 8px; line-height:1.7; white-space:pre-wrap; overflow-wrap:anywhere; }
.vp-confirm-item { padding:18px 0; border-bottom:1px solid #e5eaf0; margin-bottom:14px; }
.vp-rule-row { display:flex; align-items:center; flex-wrap:wrap; gap:8px; margin:12px 0; }
.vp-rule-row .el-select { width:170px; }
.vp-source-note { font-size:12px; color:#8190a3; line-height:1.7; margin:0 0 16px; }
.vp-records { padding: 20px; }
.vp-list-heading { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; margin-bottom:18px; }
.vp-list-heading h3 { margin:0; font-size:16px; }
.vp-list-heading h3 span { margin-left:8px; font-weight:400; }
.vp-pagination { margin-top:20px; justify-content:flex-end; overflow:auto; }
.vp-due { color:var(--el-color-warning); margin:5px 0 0; }
.vp-detail-title { display:flex; align-items:center; gap:12px; margin-bottom:20px; }
.vp-detail-title h2 { margin:0; }
.vp-detail-heading { margin-top:24px; font-size:15px; }
.vp-basis { white-space:pre-wrap; overflow-wrap:anywhere; line-height:1.9; }
:deep(.el-table .tiny) { display:block; margin-top:5px; }
@media(max-width:600px) { .vp-records { padding:12px; } .vp-pagination { justify-content:flex-start; } }

.viewpoints-page { --vp-border: #e5eaf0; --vp-muted: #8190a3; }
.vp-summary { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); background:#fff; border:1px solid var(--vp-border); border-radius:12px; margin:8px 0 24px; padding:24px 0; }
.vp-summary > div { padding:0 28px; border-right:1px solid var(--vp-border); min-width:0; }
.vp-summary > div:last-child { border-right:0; }
.vp-summary span { display:block; font-size:13px; color:#64748b; margin-bottom:12px; }
.vp-summary strong { display:block; font-size:30px; line-height:1.2; font-weight:650; color:#24364b; font-variant-numeric:tabular-nums; letter-spacing:-.8px; }
.vp-summary > div:first-child strong { color:var(--el-color-primary); }
.vp-summary small { font-size:12px; font-weight:400; color:var(--vp-muted); margin-left:7px; letter-spacing:0; }
.vp-summary p { margin:10px 0 0; font-size:12px; color:var(--vp-muted); line-height:1.6; }
.vp-tabs { margin-bottom:4px; }
.vp-tabs :deep(.el-tabs__nav-wrap::after) { height:1px; background:var(--vp-border); }
.vp-tabs :deep(.el-tabs__item) { font-size:14px; height:46px; }
.vp-records { border:1px solid var(--vp-border); border-radius:12px; box-shadow:none; padding:0; overflow:hidden; }
.vp-list-heading { padding:20px 22px 16px; margin:0; }
.vp-list-heading h3 { color:#334155; font-size:14px; }
.vp-list-heading :deep(.el-radio-button__inner) { box-shadow:none; border-color:transparent; background:#f2f5f8; color:#66758a; padding:8px 14px; }
.vp-list-heading :deep(.el-radio-button.is-active .el-radio-button__inner) { background:var(--el-color-primary-light-9); color:var(--el-color-primary); border-color:transparent; box-shadow:none; }
.vp-filters { margin:0 22px 20px; padding:0; background:transparent; border:0; gap:10px; display:flex; flex-wrap:wrap; }
.vp-filters :deep(.el-input__wrapper), .vp-filters :deep(.el-select__wrapper) { border-radius:7px; min-height:34px; }
.vp-records :deep(.el-table) { font-size:13px; }
.vp-records :deep(.el-table th.el-table__cell) { font-weight:500; color:#758297; height:42px; }
.vp-records :deep(.el-table td.el-table__cell) { padding:16px 0; color:#37465b; }
.vp-records :deep(.el-table .cell) { padding-left:16px; padding-right:16px; }
.vp-records :deep(.el-table__empty-block) { min-height:230px; }
.vp-records :deep(.el-tag) { border:0; border-radius:4px; font-weight:500; }
.vp-pagination { margin:0; padding:18px 22px; }
.vp-stat-note { grid-column:1 / -1; margin:0; padding:4px 0 0; font-size:12px; color:var(--vp-muted); }
.vp-portrait { border:1px solid var(--vp-border); border-radius:12px; box-shadow:none; }
@media(max-width:1050px) { .vp-summary > div { padding:0 18px; } .vp-summary p { min-height:38px; } }
@media(max-width:650px) { .vp-summary { grid-template-columns:repeat(2,minmax(0,1fr)); gap:20px 0; padding:20px 0; } .vp-summary > div:nth-child(2) { border-right:0; } .vp-summary strong { font-size:26px; } .vp-summary p { min-height:0; } .vp-list-heading { padding:16px; } .vp-filters { margin:0 16px 16px; } .vp-filters > .el-select { flex:1 1 40%; width:auto !important; } .vp-filters > .el-input { flex:1 1 100%; width:auto !important; } }

.vp-extract-actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.vp-ai-task{display:flex;gap:16px;flex-wrap:wrap;padding:12px 4px;font-size:13px;color:#64748b}.vp-original{margin:12px 0}.vp-original summary{cursor:pointer;font-size:12px;color:#8490a2}
.vp-toolbar { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:16px 20px; background:#fff; border:1px solid var(--vp-border); border-radius:10px; }
.vp-date-field { display:flex; align-items:center; gap:14px; font-size:13px; color:#64748b; }
.vp-date-field :deep(.el-date-editor) { width:300px; flex:none; }
.vp-summary { display:flex; align-items:center; gap:32px; padding:20px 4px; margin:0; background:transparent; border:0; border-radius:0; }
.vp-summary > div { display:flex; align-items:baseline; gap:12px; padding:0 28px 0 0; border-right:1px solid #dfe5ed; }
.vp-summary span { margin:0; font-size:13px; color:#8490a2; }
.vp-summary strong { font-size:22px; font-weight:600; letter-spacing:-.4px; color:#334155; }
.vp-summary > div:first-child strong { color:#334155; }
.vp-tabs { margin:0; padding:0 20px; border:1px solid var(--vp-border); border-bottom:0; border-radius:10px 10px 0 0; background:#fff; }
.vp-tabs :deep(.el-tabs__header) { margin:0; }
.vp-tabs :deep(.el-tabs__item) { height:52px; }
.vp-tabs :deep(.el-tabs__nav-wrap::after) { background:#eef1f5; }
.vp-records { border-top:0; border-radius:0 0 10px 10px; }
.vp-list-heading { padding:14px 20px; }
.vp-list-heading h3 { font-size:13px; font-weight:500; color:#8490a2; }
.vp-list-heading>div:last-child { display:flex; align-items:center; gap:18px; }
.vp-records :deep(.el-table__empty-block) { min-height:300px; }
.vp-records :deep(.el-table__empty-text) { font-size:13px; color:#a0aaba; }
@media(max-width:650px) { .vp-toolbar { flex-wrap:wrap;padding:14px; } .vp-date-field { width:100%;gap:8px; } .vp-date-field :deep(.el-date-editor) { width:auto;flex:1;min-width:0; } .vp-summary { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;padding:18px 4px; } .vp-summary>div { padding:0 10px;gap:8px; } .vp-tabs { padding:0 14px; } }
.vp-portraits { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.vp-portrait { padding: 18px 20px; }
.panel-header h3 { margin: 0 0 4px; font-size: 15px; }
@media (max-width: 1100px) { .vp-portraits { grid-template-columns: minmax(0, 1fr); } }

/* 与全站终端皮肤对齐：方角、墨蓝强调、表头不填底色（放在最后以覆盖上面的早期分层样式） */
.viewpoints-page { --vp-border: var(--line); --vp-muted: var(--ink-3); }
.vp-toolbar { border-radius: var(--radius); padding: 12px 16px; border-color: var(--line); }
.vp-date-field { color: var(--ink-3); }
.vp-summary > div { border-right-color: var(--line); padding-right: 24px; gap: 10px; }
.vp-summary span { color: var(--ink-3); font-size: 12px; }
.vp-summary strong { font-size: 22px; color: var(--ink-1); letter-spacing: -0.02em; }
.vp-summary > div:first-child strong { color: var(--ink-1); }
.vp-tabs { padding: 0 16px; border-radius: var(--radius) var(--radius) 0 0; border-color: var(--line); }
.vp-tabs :deep(.el-tabs__item) { height: 42px; font-size: 13px; }
.vp-tabs :deep(.el-tabs__nav-wrap::after) { background: var(--line-2); }
.vp-records { border-color: var(--line); border-radius: 0 0 var(--radius) var(--radius); }
.vp-list-heading { padding: 12px 16px; }
.vp-list-heading h3 { font-size: 13px; color: var(--ink-2); }
.vp-filters { margin: 0 16px 14px; }
.vp-filters :deep(.el-input__wrapper), .vp-filters :deep(.el-select__wrapper) { border-radius: var(--radius); min-height: 32px; }

.vp-records :deep(.el-table th.el-table__cell) { color: var(--ink-3); font-size: 12px; height: 38px; }
.vp-records :deep(.el-table td.el-table__cell) { padding: 10px 0; color: var(--ink-1); }
.vp-records :deep(.el-table .cell) { padding-left: 16px; padding-right: 16px; }
.vp-records :deep(.el-tag) { border-radius: var(--radius); }
.vp-pagination { padding: 12px 16px; }
.vp-list-heading :deep(.el-radio-button__inner) { border-radius: var(--radius); background: var(--el-fill-color-light); color: var(--ink-2); }
.vp-list-heading :deep(.el-radio-button.is-active .el-radio-button__inner) { background: var(--accent-soft); color: var(--accent); }
.vp-portrait { border-radius: var(--radius); border-color: var(--line); }
.vp-ai-task { color: var(--ink-2); }
.vp-original summary { color: var(--ink-3); }
.vp-stat-note { color: var(--ink-3); }
</style>
