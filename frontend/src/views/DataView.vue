<template>
  <div>
    <PageHead
      title="手工数据录入"
      description="同花顺 / Wind 等数据来源在这里取数入库；配好接口与计划后服务端按时自动同步，CSV 仅作备用通道。"
    >
      <el-button @click="router.push('/data/indicators')">指标查询</el-button>
      <el-button @click="openCsv">导入 CSV</el-button>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </PageHead>

    <div class="card-grid src-grid">
      <div v-for="source in sources" :key="source.key" class="panel src-card">
        <div class="src-head">
          <div>
            <h3>{{ source.name }}</h3>
            <p class="caption">{{ source.product || '—' }}</p>
          </div>
          <div class="row" style="gap: 6px">
            <el-tag v-if="!source.enabled" size="small" type="info" effect="plain" disable-transitions>已停用</el-tag>
            <el-tag :type="source.rows ? 'success' : 'info'" size="small" disable-transitions>
              {{ source.rows ? '已同步' : '待同步' }}
            </el-tag>
          </div>
        </div>
        <div class="src-facts">
          <span>数据点 <b>{{ source.rows }}</b></span>
          <span>指标 <b>{{ source.indicators }}</b></span>
          <span>最新 <b>{{ source.latest || '—' }}</b></span>
        </div>
        <p class="caption src-channel">{{ source.channel || '未填写取数通道说明' }}</p>
        <div class="row" style="margin-top: 12px">
          <el-button type="primary" size="small" :disabled="!canSync || !source.enabled" @click="openSync(source)">
            同步数据
          </el-button>
          <el-button v-if="canConfig" link size="small" @click="openSource(source)">编辑</el-button>
          <span class="tiny">上次同步 {{ localTime(source.last_sync) }}</span>
        </div>
      </div>

      <button v-if="canConfig" type="button" class="src-add" @click="openSource(null)">
        <span>+</span>
        添加数据来源
      </button>
    </div>

    <div v-if="canConfig" class="panel">
      <div class="panel-header">
        <h3>取数配置</h3>
        <div class="row">
          <span class="hint">配好接口与计划，服务端自己取数入库</span>
          <el-button type="primary" size="small" @click="openConfig(null)">新建配置</el-button>
        </div>
      </div>
      <el-table :data="configs" empty-text="还没有取数配置" size="small">
        <el-table-column prop="name" label="名称" min-width="150">
          <template #default="{ row }">
            <span class="ellipsis" style="display: block" :title="row.name">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="96">
          <template #default="{ row }">{{ row.source_name }}</template>
        </el-table-column>
        <el-table-column label="方式" width="132">
          <template #default="{ row }">
            <span class="tiny">{{ row.kind_label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="接口" min-width="180">
          <template #default="{ row }">
            <span class="tiny ellipsis" style="display: block" :title="row.base_url">{{ row.base_url }}</span>
          </template>
        </el-table-column>
        <el-table-column label="范围" min-width="140">
          <template #default="{ row }">
            <span class="tiny ellipsis" style="display: block" :title="configScope(row)">{{ configScope(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计划" width="118">
          <template #default="{ row }">
            <span class="tiny">{{ planText(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上次执行" width="150">
          <template #default="{ row }">
            <span class="tiny">{{ row.last_run || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="82">
          <template #default="{ row }">
            <el-tag :type="configTag(row)" size="small" disable-transitions>{{ row.last_status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="236">
          <template #default="{ row }">
            <el-button link type="primary" size="small" :loading="runningId === row.id" @click="runConfig(row)">
              执行
            </el-button>
            <el-button link size="small" :loading="testingId === row.id" @click="testConfig(row)">试连</el-button>
            <el-button link size="small" @click="openConfig(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="removeConfig(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <p class="caption" style="margin-top: 10px">
        凭据只保存在服务端数据库，接口只回传掩码；执行结果会写进下方同步记录，失败原因也一并记录。
      </p>
    </div>

    <div class="panel">
      <div class="panel-header">
        <h3>同步记录</h3>
        <span class="hint">共 {{ jobTotal }} 条</span>
      </div>

      <div class="filter-bar job-filter">
        <el-select v-model="jobFilter.source" clearable placeholder="全部来源" style="width: 132px" @change="queryJobs(1)">
          <el-option v-for="item in sources" :key="item.key" :label="item.name" :value="item.key" />
        </el-select>
        <el-select v-model="jobFilter.status" clearable placeholder="全部状态" style="width: 118px" @change="queryJobs(1)">
          <el-option v-for="item in jobStatuses" :key="item" :label="item" :value="item" />
        </el-select>
        <el-input
          v-model="jobFilter.q"
          placeholder="搜说明或范围"
          clearable
          style="width: 190px"
          @keyup.enter="queryJobs(1)"
          @clear="queryJobs(1)"
        />
        <el-date-picker
          v-model="jobFilter.range"
          type="daterange"
          value-format="YYYY-MM-DD"
          unlink-panels
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          style="width: 240px"
          @change="queryJobs(1)"
        />
        <el-button type="primary" @click="queryJobs(1)">查询</el-button>
        <el-button @click="resetJobFilter">重置</el-button>
      </div>

      <el-table :data="jobs" empty-text="没有匹配的同步记录" size="small">
        <el-table-column prop="id" label="编号" width="62" />
        <el-table-column label="来源" width="92">
          <template #default="{ row }">{{ row.source_name }}</template>
        </el-table-column>
        <el-table-column label="范围" min-width="200">
          <template #default="{ row }">
            <span class="ellipsis" style="display: block" :title="scopeText(row)">{{ scopeText(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="区间" width="82">
          <template #default="{ row }">近 {{ row.scope?.days || '—' }} 日</template>
        </el-table-column>
        <el-table-column label="状态" width="86">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small" disable-transitions>{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="数据点" width="80" align="right">
          <template #default="{ row }">
            <span v-if="row.status === '已完成'">{{ row.rows }}</span>
            <span v-else class="tiny">—</span>
          </template>
        </el-table-column>
        <el-table-column label="登记时间" width="150">
          <template #default="{ row }">{{ localTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="说明" min-width="170">
          <template #default="{ row }">
            <button type="button" class="job-note" :title="row.message || ''" @click="openJob(row)">
              {{ row.message || (row.status === '待执行' ? '等待取数通道回填' : '—') }}
            </button>
          </template>
        </el-table-column>
      </el-table>

      <div class="job-pager">
        <el-pagination
          layout="prev, pager, next"
          :current-page="jobPage"
          :page-size="jobSize"
          :total="jobTotal"
          background
          @current-change="queryJobs"
        />
      </div>
    </div>

    <el-dialog v-model="syncVisible" :title="`从 ${activeSource?.name || ''} 同步`" width="540px">
      <el-form label-width="72px" label-position="left" @submit.prevent>
        <el-form-item label="范围">
          <el-select
            v-model="scopeItems"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            :placeholder="scopePlaceholder"
            style="width: 100%"
          >
            <el-option v-for="item in scopeOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="指标">
          <el-checkbox-group v-model="scopeMetrics">
            <el-checkbox v-for="metric in metrics" :key="metric.key" :label="metric.key">
              {{ metric.label }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="区间">
          <el-radio-group v-model="scopeDays">
            <el-radio-button :label="5">5 个交易日</el-radio-button>
            <el-radio-button :label="10">10 个</el-radio-button>
            <el-radio-button :label="20">20 个</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <el-alert type="info" :closable="false" show-icon>
        <template #title>
          这里登记的是待执行作业，由已授权通道回填；若希望服务端自己按时取数，请在上方「取数配置」里配接口与计划。
        </template>
      </el-alert>
      <template #footer>
        <el-button @click="syncVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitSync">登记同步</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="csvVisible" title="导入 CSV" width="520px" @closed="resetCsv">
      <p class="caption">
        UTF-8 CSV，表头 source,indicator,date,value,unit；日期 YYYY-MM-DD，数值为有限数字，
        整批校验失败不入库。
      </p>
      <div class="csv-pick" @click="fileInput?.click()">
        <el-button @click.stop="fileInput?.click()">选择文件</el-button>
        <span v-if="fileName" class="caption ellipsis" :title="fileName">{{ fileName }}</span>
        <span v-else class="tiny">未选择文件 · 仅支持 .csv</span>
        <input ref="fileInput" type="file" accept=".csv" class="csv-native" @change="onFileChange" />
      </div>
      <p class="caption csv-sample">示例：Wind,螺纹钢库存,2026-11-16,100,万吨（仅格式示例）</p>
      <template #footer>
        <el-button @click="csvVisible = false">取消</el-button>
        <el-button type="primary" :loading="busy" :disabled="!picked" @click="submit">导入</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="sourceVisible" :title="sourceForm.id ? '编辑数据来源' : '添加数据来源'" width="520px">
      <el-form label-width="96px" label-position="left" @submit.prevent>
        <el-form-item label="名称">
          <el-input v-model="sourceForm.name" maxlength="30" placeholder="入库标签，如：同花顺 / 卓创资讯" />
        </el-form-item>
        <el-form-item label="标识">
          <el-input v-model="sourceForm.key" maxlength="24" placeholder="字母数字下划线，如 ifind / zhuochuang" />
        </el-form-item>
        <el-form-item label="产品">
          <el-input v-model="sourceForm.product" maxlength="40" placeholder="如 iFinD / 金融终端" />
        </el-form-item>
        <el-form-item label="通道说明">
          <el-input v-model="sourceForm.channel" maxlength="120" placeholder="这条通道怎么取数，给同事看的" />
        </el-form-item>
        <el-form-item label="可选范围">
          <el-radio-group v-model="sourceForm.scope_mode">
            <el-radio-button label="commodity">按品种库</el-radio-button>
            <el-radio-button label="custom">自定义项</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="sourceForm.scope_mode === 'custom'" label="自定义项">
          <el-input
            v-model="sourceForm.scope_text"
            type="textarea"
            :rows="4"
            placeholder="每行一个，如：南华商品指数 / 螺纹钢现货价"
          />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="sourceForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="sourceForm.id" type="danger" text @click="removeSource">删除</el-button>
        <el-button @click="sourceVisible = false">取消</el-button>
        <el-button type="primary" :loading="sourceSaving" @click="saveSource">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="configVisible"
      :title="configForm.id ? '编辑取数配置' : '新建取数配置'"
      width="640px"
      top="6vh"
      class="cfg-dialog"
    >
      <el-alert
        v-if="testResult"
        class="cfg-alert"
        :type="testResult.ok ? 'success' : 'error'"
        :title="testResult.message"
        :description="testResult.ok
          ? `耗时 ${(testResult.ms / 1000).toFixed(1)} 秒；样本 ${testResult.sample.length} 条，如 ${testResult.sample[0]?.indicator} ${testResult.sample[0]?.date} = ${testResult.sample[0]?.value}`
          : ''"
        show-icon
        :closable="false"
      />

      <el-form label-width="96px" label-position="left" @submit.prevent>
        <el-form-item label="名称">
          <el-input v-model="configForm.name" maxlength="40" placeholder="如：同花顺-黑色日盘" />
        </el-form-item>
        <el-form-item label="数据来源">
          <el-select v-model="configForm.source" placeholder="选择来源" style="width: 100%">
            <el-option v-for="item in sources" :key="item.key" :label="item.name" :value="item.key" />
          </el-select>
        </el-form-item>
        <el-form-item label="取数方式">
          <el-select v-model="configForm.kind" style="width: 100%">
            <el-option v-for="item in kinds" :key="item.key" :label="item.label" :value="item.key" />
          </el-select>
        </el-form-item>
        <el-form-item label="接口地址">
          <el-input v-model="configForm.base_url" placeholder="https://... 可用 {code} {metric} {startdate} {enddate}" />
        </el-form-item>
        <el-form-item label="账号">
          <el-input v-model="configForm.account" placeholder="用户名 / AppID，可留空" />
        </el-form-item>
        <el-form-item label="密钥">
          <el-input
            v-model="configForm.secret"
            type="password"
            show-password
            autocomplete="new-password"
            :placeholder="configForm.secret_masked ? `已保存 ${configForm.secret_masked}，留空不改` : '密码 / refresh_token / apikey'"
          />
        </el-form-item>

        <el-divider content-position="left">同步范围</el-divider>
        <el-form-item label="品种">
          <el-select
            v-model="configForm.items"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            placeholder="选择品种或自定义项"
            style="width: 100%"
          >
            <el-option v-for="item in configOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="指标">
          <el-checkbox-group v-model="configForm.metrics">
            <el-checkbox v-for="metric in metrics" :key="metric.key" :label="metric.key">
              {{ metric.label }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="区间">
          <el-radio-group v-model="configForm.days">
            <el-radio-button :label="5">5 个交易日</el-radio-button>
            <el-radio-button :label="10">10 个</el-radio-button>
            <el-radio-button :label="20">20 个</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="代码后缀">
          <el-input v-model="configForm.code_suffix" placeholder="如 .SHF（请求里 {code} 会拼上），可留空" />
        </el-form-item>

        <el-divider content-position="left">执行计划</el-divider>
        <el-form-item label="频率">
          <el-select v-model="configForm.freq" style="width: 100%">
            <el-option v-for="item in freqs" :key="item.key" :label="item.label" :value="item.key" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="configForm.freq !== 'manual'" label="执行时间">
          <el-time-picker v-model="configForm.run_at" format="HH:mm" value-format="HH:mm" placeholder="08:30" />
          <el-select
            v-if="configForm.freq === 'weekly'"
            v-model="configForm.weekday"
            style="width: 120px; margin-left: 10px"
          >
            <el-option v-for="(name, index) in WEEKDAYS" :key="name" :label="name" :value="index + 1" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="configForm.enabled" />
        </el-form-item>

        <el-collapse>
          <el-collapse-item title="高级：请求模板与响应解析" name="adv">
            <el-form-item label="请求方式">
              <el-radio-group v-model="configForm.method">
                <el-radio-button label="GET">GET</el-radio-button>
                <el-radio-button label="POST">POST</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="请求头">
              <el-input v-model="configForm.headers" type="textarea" :rows="2" placeholder='{"Authorization": "Bearer {secret}"}' />
            </el-form-item>
            <el-form-item v-if="configForm.method === 'POST'" label="请求体">
              <el-input v-model="configForm.body" type="textarea" :rows="3" placeholder='{"code": "{code}", "field": "{metric}"}' />
            </el-form-item>
            <el-form-item label="数据路径">
              <el-input v-model="configForm.points_path" placeholder="响应里数组的位置，如 data.rows；留空表示响应本身就是数组" />
            </el-form-item>
            <el-form-item label="日期字段">
              <el-input v-model="configForm.date_field" placeholder="date" />
            </el-form-item>
            <el-form-item label="数值字段">
              <el-input v-model="configForm.value_field" placeholder="value" />
            </el-form-item>
            <el-form-item label="指标命名">
              <el-input v-model="configForm.indicator_template" placeholder="{item}{metric_label}" />
            </el-form-item>
            <el-form-item label="单位">
              <el-input v-model="configForm.unit" placeholder="留空按指标默认单位" />
            </el-form-item>
            <el-form-item label="字段映射">
              <el-input v-model="configForm.field_map" type="textarea" :rows="2" placeholder='{"close": "close", "open_interest": "openInterest"}' />
            </el-form-item>
          </el-collapse-item>
        </el-collapse>
      </el-form>

      <template #footer>
        <el-button :loading="testingId === 'form'" @click="testForm">试连</el-button>
        <el-button @click="configVisible = false">取消</el-button>
        <el-button type="primary" :loading="configSaving" @click="saveConfig">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="jobVisible" title="同步记录详情" width="560px">
      <div v-if="activeJob" class="job-detail">
        <div class="job-detail-row"><span>编号</span><b>#{{ activeJob.id }}</b></div>
        <div class="job-detail-row"><span>来源</span><b>{{ activeJob.source_name }}</b></div>
        <div class="job-detail-row"><span>状态</span>
          <el-tag :type="statusType(activeJob.status)" size="small" disable-transitions>{{ activeJob.status }}</el-tag>
        </div>
        <div class="job-detail-row"><span>范围</span><b>{{ scopeText(activeJob) }}</b></div>
        <div class="job-detail-row"><span>区间</span><b>近 {{ activeJob.scope?.days || '—' }} 个交易日</b></div>
        <div class="job-detail-row"><span>数据点</span>
          <b>{{ activeJob.rows || 0 }} 行（新增 {{ activeJob.inserted || 0 }}、更新 {{ activeJob.updated || 0 }}）</b>
        </div>
        <div class="job-detail-row"><span>触发方式</span>
          <b>{{ activeJob.scope?.trigger === 'schedule' ? '定时自动' : activeJob.scope?.config_id ? '配置手动执行' : '页面登记' }}</b>
        </div>
        <div class="job-detail-row"><span>登记</span><b>{{ localTime(activeJob.created_at) }} · {{ activeJob.operator }}</b></div>
        <div class="job-detail-row"><span>完成</span><b>{{ localTime(activeJob.finished_at) }}</b></div>
        <p class="caption" style="margin-top: 10px">说明</p>
        <p class="job-detail-note">{{ activeJob.message || '—' }}</p>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import PageHead from '../components/PageHead.vue';
import { api } from '../api';
import { commodities, refresh } from '../store/session';
import { localTime } from '../utils/format';

const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
const router = useRouter();

const sources = ref([]);
const metrics = ref([]);
const kinds = ref([]);
const freqs = ref([]);
const configs = ref([]);
const canSync = ref(false);
const canConfig = ref(false);
const loading = ref(false);

const syncVisible = ref(false);
const submitting = ref(false);
const activeSource = ref(null);
const scopeItems = ref([]);
const scopeMetrics = ref([]);
const scopeDays = ref(10);

const csvVisible = ref(false);
const fileInput = ref(null);
const fileName = ref('');
const busy = ref(false);
const picked = ref(null);

const sourceVisible = ref(false);
const sourceSaving = ref(false);
const sourceForm = reactive({
  id: null, key: '', name: '', product: '', channel: '',
  scope_mode: 'commodity', scope_text: '', enabled: true,
});

const configVisible = ref(false);
const configSaving = ref(false);
const testingId = ref('');
const runningId = ref('');
const testResult = ref(null);
const configForm = reactive(emptyConfig());

const jobs = ref([]);
const jobTotal = ref(0);
const jobPage = ref(1);
const jobSize = ref(20);
const jobStatuses = ref(['待执行', '执行中', '已完成', '失败']);
const jobFilter = reactive({ source: '', status: '', q: '', range: null });
const jobVisible = ref(false);
const activeJob = ref(null);

const leafCommodities = computed(() =>
  commodities.value.filter(item => item.code && item.enabled !== 0).map(item => item.name)
);

const scopeOptions = computed(() => {
  const source = activeSource.value;
  if (!source) return leafCommodities.value;
  return source.scope_mode === 'custom' && source.scope_items?.length
    ? source.scope_items
    : leafCommodities.value;
});
const scopePlaceholder = computed(() =>
  activeSource.value?.scope_mode === 'custom' ? '选择指数或指标' : '选择品种'
);

/* 配置弹窗里的品种候选：跟随所选来源的范围模式 */
const configOptions = computed(() => {
  const source = sources.value.find(item => item.key === configForm.source);
  if (source?.scope_mode === 'custom' && source.scope_items?.length) return source.scope_items;
  return leafCommodities.value;
});

function emptyConfig() {
  return {
    id: null, name: '', source: '', kind: 'generic_json', base_url: '', account: '',
    secret: '', secret_masked: '', items: [], metrics: ['close'], days: 10, code_suffix: '',
    freq: 'manual', run_at: '08:30', weekday: 1, enabled: true,
    method: 'GET', headers: '{}', body: '', points_path: 'data', date_field: 'date',
    value_field: 'value', indicator_template: '{item}{metric_label}', unit: '', field_map: '',
  };
}

function scopeText(row) {
  const items = row.scope?.items || [];
  if (!items.length) return '—';
  return items.length > 6 ? `${items.slice(0, 6).join('、')} 等 ${items.length} 项` : items.join('、');
}

function configScope(row) {
  const scope = row.scope || {};
  const items = scope.items || [];
  const labels = (scope.metrics || []).map(key => metrics.value.find(m => m.key === key)?.label || key);
  const head = items.length > 3 ? `${items.slice(0, 3).join('、')} 等 ${items.length} 个` : items.join('、');
  return `${head || '—'} · ${labels.join('/') || '—'} · 近 ${scope.days || '—'} 日`;
}

function planText(row) {
  if (!row.enabled) return '已停用';
  if (row.freq === 'daily') return `每日 ${row.run_at}`;
  if (row.freq === 'weekly') return `每${WEEKDAYS[row.weekday - 1] || '周'} ${row.run_at}`;
  return '仅手动';
}

function configTag(row) {
  return { 成功: 'success', 失败: 'danger', 未运行: 'info' }[row.last_status] || 'info';
}

function statusType(status) {
  return { 已完成: 'success', 未执行: 'warning', 待执行: 'warning', 执行中: 'warning', 失败: 'danger' }[status] || 'info';
}

async function load() {
  loading.value = true;
  try {
    const result = await api('data/sources');
    sources.value = result.sources || [];
    metrics.value = result.metrics || [];
    kinds.value = result.kinds || [];
    freqs.value = result.freqs || [];
    configs.value = result.configs || [];
    canSync.value = Boolean(result.can_sync);
    canConfig.value = Boolean(result.can_config);
    if (canSync.value) queryJobs(jobPage.value);
  } catch (error) {
    ElMessage.error(error.message || '读取数据源状态失败');
  } finally {
    loading.value = false;
  }
}

async function queryJobs(page = 1) {
  jobPage.value = page;
  const params = new URLSearchParams({ page: String(page), size: String(jobSize.value) });
  if (jobFilter.source) params.set('source', jobFilter.source);
  if (jobFilter.status) params.set('status', jobFilter.status);
  if (jobFilter.q) params.set('q', jobFilter.q);
  if (jobFilter.range?.[0]) params.set('start', jobFilter.range[0]);
  if (jobFilter.range?.[1]) params.set('end', jobFilter.range[1]);
  try {
    const result = await api(`data/jobs?${params.toString()}`);
    jobs.value = result.jobs || [];
    jobTotal.value = result.total || 0;
    jobStatuses.value = result.statuses || jobStatuses.value;
  } catch (error) {
    ElMessage.error(error.message || '读取同步记录失败');
  }
}

function resetJobFilter() {
  jobFilter.source = '';
  jobFilter.status = '';
  jobFilter.q = '';
  jobFilter.range = null;
  queryJobs(1);
}

function openJob(row) {
  activeJob.value = row;
  jobVisible.value = true;
}

/* ---------- 页面登记同步（由已授权通道回填） ---------- */
function openSync(source) {
  activeSource.value = source;
  scopeItems.value = source.scope_mode === 'custom' && source.scope_items?.length
    ? source.scope_items.slice(0, 1)
    : leafCommodities.value.slice(0, 6);
  scopeMetrics.value = ['close', 'settle', 'volume', 'open_interest'];
  scopeDays.value = 10;
  syncVisible.value = true;
}

async function submitSync() {
  if (!scopeItems.value.length) return ElMessage.warning('请选择至少一个品种或指标');
  if (!scopeMetrics.value.length) return ElMessage.warning('请选择至少一个指标');
  submitting.value = true;
  try {
    const result = await api('data/jobs', {
      source: activeSource.value?.key,
      items: scopeItems.value,
      metrics: scopeMetrics.value,
      days: scopeDays.value,
    });
    syncVisible.value = false;
    await queryJobs(1);
    ElMessage.success(`已登记同步作业 #${result.job?.id}，取数回填后自动入库`);
  } catch (error) {
    ElMessage.error(error.message || '登记同步作业失败');
  } finally {
    submitting.value = false;
  }
}

/* ---------- 数据来源维护 ---------- */
function openSource(source) {
  Object.assign(sourceForm, {
    id: source?.id || null,
    key: source?.key || '',
    name: source?.name || '',
    product: source?.product || '',
    channel: source?.channel || '',
    scope_mode: source?.scope_mode || 'commodity',
    scope_text: (source?.scope_items || []).join('\n'),
    enabled: source ? Boolean(source.enabled) : true,
  });
  sourceVisible.value = true;
}

async function saveSource() {
  const items = sourceForm.scope_text.split('\n').map(x => x.trim()).filter(Boolean);
  sourceSaving.value = true;
  try {
    await api('data/sources', {
      id: sourceForm.id || undefined,
      key: sourceForm.key, name: sourceForm.name,
      product: sourceForm.product, channel: sourceForm.channel,
      scope_mode: sourceForm.scope_mode,
      scope_items: sourceForm.scope_mode === 'custom' ? items : [],
      enabled: sourceForm.enabled,
    });
    sourceVisible.value = false;
    await load();
    ElMessage.success('数据来源已保存');
  } catch (error) {
    ElMessage.error(error.message || '保存数据来源失败');
  } finally {
    sourceSaving.value = false;
  }
}

async function removeSource() {
  try {
    await ElMessageBox.confirm(
      `删除「${sourceForm.name}」后不可恢复；已有配置或入库数据时不能删除。`, '删除数据来源？',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    );
  } catch {
    return;
  }
  try {
    await api('data/sources/delete', { id: sourceForm.id });
    sourceVisible.value = false;
    await load();
    ElMessage.success('已删除');
  } catch (error) {
    ElMessage.error(error.message || '删除失败');
  }
}

/* ---------- 取数配置 ---------- */
function openConfig(config) {
  testResult.value = null;
  Object.assign(configForm, emptyConfig());
  if (config) {
    const options = config.options || {};
    Object.assign(configForm, {
      id: config.id, name: config.name, source: config.source, kind: config.kind,
      base_url: config.base_url, account: config.account,
      secret: '', secret_masked: config.secret_masked,
      items: config.scope?.items || [], metrics: config.scope?.metrics || ['close'],
      days: config.scope?.days || 10, code_suffix: config.scope?.code_suffix || '',
      freq: config.freq, run_at: config.run_at || '08:30', weekday: config.weekday || 1,
      enabled: Boolean(config.enabled),
      method: options.method || 'GET', headers: options.headers || '{}', body: options.body || '',
      points_path: options.points_path ?? 'data', date_field: options.date_field || 'date',
      value_field: options.value_field || 'value',
      indicator_template: options.indicator_template || '{item}{metric_label}',
      unit: options.unit || '',
      field_map: options.field_map && Object.keys(options.field_map).length
        ? JSON.stringify(options.field_map) : '',
    });
  } else if (sources.value.length) {
    configForm.source = sources.value[0].key;
    configForm.name = `${sources.value[0].name} 自动同步`;
  }
  configVisible.value = true;
}

function configPayload() {
  let fieldMap = {};
  if (configForm.field_map.trim()) {
    try {
      fieldMap = JSON.parse(configForm.field_map);
    } catch {
      throw new Error('字段映射需为 JSON，如 {"close": "close"}');
    }
  }
  const payload = {
    id: configForm.id || undefined,
    name: configForm.name, source: configForm.source, kind: configForm.kind,
    base_url: configForm.base_url, account: configForm.account,
    scope: {
      items: configForm.items, metrics: configForm.metrics,
      days: configForm.days, code_suffix: configForm.code_suffix,
    },
    options: {
      method: configForm.method, headers: configForm.headers, body: configForm.body,
      points_path: configForm.points_path, date_field: configForm.date_field,
      value_field: configForm.value_field, indicator_template: configForm.indicator_template,
      unit: configForm.unit, field_map: fieldMap,
    },
    freq: configForm.freq, run_at: configForm.run_at, weekday: configForm.weekday,
    enabled: configForm.enabled,
  };
  if (configForm.secret) payload.secret = configForm.secret;
  return payload;
}

async function saveConfig() {
  if (!configForm.items.length) return ElMessage.warning('请选择至少一个品种');
  if (!configForm.metrics.length) return ElMessage.warning('请选择至少一个指标');
  let payload;
  try {
    payload = configPayload();
  } catch (error) {
    return ElMessage.warning(error.message);
  }
  configSaving.value = true;
  try {
    await api('data/configs', payload);
    configVisible.value = false;
    await load();
    ElMessage.success('配置已保存');
  } catch (error) {
    ElMessage.error(error.message || '保存配置失败');
  } finally {
    configSaving.value = false;
  }
}

async function testForm() {
  let payload;
  try {
    payload = configPayload();
  } catch (error) {
    return ElMessage.warning(error.message);
  }
  testingId.value = 'form';
  testResult.value = null;
  try {
    testResult.value = await api('data/configs/test', payload);
    if (testResult.value.ok) ElMessage.success(testResult.value.message);
    else ElMessage.error(testResult.value.message);
  } catch (error) {
    testResult.value = { ok: false, message: error.message || '试连失败', ms: 0, sample: [] };
    ElMessage.error(testResult.value.message);
  } finally {
    testingId.value = '';
  }
}

async function testConfig(row) {
  testingId.value = row.id;
  try {
    const result = await api('data/configs/test', { id: row.id });
    if (result.ok) ElMessage.success(result.message);
    else ElMessage.error(result.message);
  } catch (error) {
    ElMessage.error(error.message || '试连失败');
  } finally {
    testingId.value = '';
  }
}

async function runConfig(row) {
  runningId.value = row.id;
  try {
    const result = await api('data/configs/run', { id: row.id });
    if (result.ok) ElMessage.success(result.message);
    else ElMessage.warning(result.message);
    await Promise.all([load(), refresh()]);
  } catch (error) {
    ElMessage.error(error.message || '执行失败');
  } finally {
    runningId.value = '';
  }
}

async function removeConfig(row) {
  try {
    await ElMessageBox.confirm(`确定删除配置「${row.name}」？已入库的数据不受影响。`, '删除取数配置？', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    });
  } catch {
    return;
  }
  try {
    await api('data/configs/delete', { id: row.id });
    await load();
    ElMessage.success('已删除');
  } catch (error) {
    ElMessage.error(error.message || '删除失败');
  }
}

/* ---------- CSV 备用通道 ---------- */
function openCsv() {
  resetCsv();
  csvVisible.value = true;
}

function resetCsv() {
  picked.value = null;
  fileName.value = '';
  if (fileInput.value) fileInput.value.value = '';
}

function onFileChange(event) {
  picked.value = event.target.files?.[0] || null;
  fileName.value = picked.value?.name || '';
}

async function submit() {
  if (!picked.value) return ElMessage.warning('请选择 CSV 文件');
  busy.value = true;
  try {
    const result = await api('import', { csv: await picked.value.text() });
    await Promise.all([refresh(), load()]);
    csvVisible.value = false;
    ElMessage.success(
      `已处理 ${result.count} 行：新增 ${result.inserted ?? 0}、更新 ${result.updated ?? 0}、重复跳过 ${result.skipped ?? 0}`
    );
  } catch (error) {
    ElMessage.error(error.message || '导入失败');
  } finally {
    busy.value = false;
  }
}

onMounted(load);
</script>
