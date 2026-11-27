<template>
  <div class="indicator-page">
    <PageContainer title="指标查询">
      <template #actions>
        <el-button :loading="loading" @click="load">刷新</el-button>
      </template>

    <div class="panel ind-filter">
      <div class="row">
        <span class="source-label">来源</span>
        <el-select v-model="selectedSources" multiple clearable filterable collapse-tags collapse-tags-tooltip
          placeholder="全部来源" aria-label="选择数据来源，可多选" class="source-select">
          <el-option v-for="item in sources" :key="item.key" :label="item.name" :value="item.key" />
        </el-select>
        <el-input v-model="keyword" placeholder="搜索指标名，如 上证指数 / 螺纹钢" clearable class="indicator-search" />
        <span class="tiny result-summary">{{ selectedSourceName }} · {{ filtered.length }} 个指标 · {{ totalPoints.toLocaleString() }} 个数据点</span>
      </div>
    </div>

    <div class="ind-body">
      <div class="panel ind-list">
        <div class="ind-list-head">
          <b>指标目录</b>
          <span class="tiny">{{ filtered.length }}</span>
        </div>
        <div class="ind-list-scroll">
          <button
            v-for="item in filtered"
            :key="item.source + '|' + item.indicator"
            type="button"
            class="ind-item"
            :class="{ on: isActive(item) }"
            @click="select(item)"
          >
            <span class="ind-name ellipsis" :title="item.indicator">{{ item.indicator }}</span>
            <span class="ind-meta">
              <span class="tiny">{{ item.source }}</span>
              <span class="tiny">{{ item.points }} 点</span>
              <span
                v-if="item.change_pct !== null && item.change_pct !== undefined"
                class="ind-chg"
                :class="item.change_pct >= 0 ? 'up' : 'down'"
              >
                {{ item.change_pct >= 0 ? '+' : '' }}{{ item.change_pct }}%
              </span>
            </span>
          </button>
          <p v-if="!filtered.length" class="caption ind-empty">
            {{ keyword.trim() ? '没有匹配的指标，换个关键字试试' : `${selectedSourceName}暂无入库指标，请先在「数据录入」同步数据` }}
          </p>
        </div>
      </div>

      <div class="panel ind-detail">
        <template v-if="current && filtered.length">
          <div class="ind-detail-head">
            <div class="grow">
              <h3 class="ellipsis" :title="current.indicator">{{ current.indicator }}</h3>
              <p class="caption">
                {{ current.source }} · 单位 {{ current.unit || '—' }}
                <span v-if="current.metric_label"> · {{ current.metric_label }}</span>
              </p>
            </div>
            <el-date-picker
              v-model="range"
              type="daterange"
              value-format="YYYY-MM-DD"
              unlink-panels
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              range-separator="至"
              style="width: 250px"
              @change="loadSeries"
            />
          </div>

          <div class="ind-stat">
            <div v-for="cell in statCells" :key="cell.label">
              <span>{{ cell.label }}</span>
              <b :class="cell.tone || ''">{{ cell.value }}</b>
            </div>
          </div>

          <div class="ind-chart">
            <svg
              v-if="chart"
              :viewBox="`0 0 ${chart.w} ${chart.h}`"
              preserveAspectRatio="none"
              role="img"
              :aria-label="`${current.indicator} 走势`"
            >
              <defs>
                <linearGradient :id="gradientId" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#409EFF" stop-opacity="0.22" />
                  <stop offset="100%" stop-color="#409EFF" stop-opacity="0" />
                </linearGradient>
              </defs>
              <line
                v-for="tick in chart.ticks"
                :key="tick.y"
                :x1="0"
                :x2="chart.w"
                :y1="tick.y"
                :y2="tick.y"
                stroke="var(--el-border-color-lighter)"
                stroke-width="1"
                vector-effect="non-scaling-stroke"
              />
              <path :d="chart.area" :fill="`url(#${gradientId})`" />
              <path
                :d="chart.line"
                fill="none"
                stroke="#409EFF"
                stroke-width="1.6"
                stroke-linejoin="round"
                stroke-linecap="round"
                vector-effect="non-scaling-stroke"
              />
              <circle
                v-for="point in chart.points"
                :key="point.date"
                :cx="point.x"
                :cy="point.y"
                r="6"
                fill="transparent"
              >
                <title>{{ point.date }}：{{ point.value }}</title>
              </circle>
            </svg>
            <p v-else class="caption ind-chart-empty">
              {{ series && series.points.length === 1 ? '只有 1 个数据点，暂不绘制走势' : '所选区间内没有数据' }}
            </p>
            <div v-if="chart" class="ind-axis">
              <span>{{ chart.first }}</span>
              <span class="tiny">最高 {{ chart.max }} · 最低 {{ chart.min }}</span>
              <span>{{ chart.last }}</span>
            </div>
          </div>

          <el-table :data="tableRows" empty-text="所选区间内没有数据" size="small" max-height="300">
            <el-table-column prop="date" label="日期" width="120" />
            <el-table-column label="数值" width="140" align="right">
              <template #default="{ row }">
                <b class="ind-num">{{ formatNumber(row.value) }}</b>
              </template>
            </el-table-column>
            <el-table-column label="较上期" width="128" align="right">
              <template #default="{ row }">
                <span v-if="row.delta !== null" class="ind-chg" :class="row.delta >= 0 ? 'up' : 'down'">
                  {{ row.delta >= 0 ? '+' : '' }}{{ formatNumber(row.delta) }}
                </span>
                <span v-else class="tiny">—</span>
              </template>
            </el-table-column>
            <el-table-column prop="uploaded_by" label="导入人" min-width="96" />
          </el-table>
        </template>
        <div v-else class="ind-placeholder">
          <p class="caption">
            {{ keyword.trim() ? '没有匹配的指标，清空关键字或切换来源后再看' : `${selectedSourceName}暂无入库指标，请先在「数据录入」同步数据` }}
          </p>
        </div>
      </div>
    </div>
    </PageContainer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import PageContainer from '../components/PageContainer.vue';
import { api } from '../api';

const METRIC_LABELS = {
  close: '收盘价', settle: '结算价', volume: '成交量', open_interest: '持仓量',
  spot: '现货价', inventory: '库存', index_close: '收盘点位',
};
const GRADIENT_ID = 'ind-area-gradient';

const indicators = ref([]);
const sources = ref([]);
const loading = ref(false);
const seriesLoading = ref(false);
const selectedSources = ref([]);
const keyword = ref('');
const current = ref(null);
const series = ref(null);
const range = ref(null);

const gradientId = GRADIENT_ID;

const filtered = computed(() => {
  const word = keyword.value.trim();
  return indicators.value.filter(item => {
    if (selectedSources.value.length && !selectedSources.value.includes(item.source_key)) return false;
    if (word && !item.indicator.includes(word)) return false;
    return true;
  });
});

const selectedSourceName = computed(() => !selectedSources.value.length ? '全部来源'
  : sources.value.filter(item => selectedSources.value.includes(item.key)).map(item => item.name).join('、'));
watch(filtered, rows => {
  if (rows.some(isActive)) return;
  if (rows.length) select(rows[0]);
  else { current.value = null; series.value = null; }
});

const totalPoints = computed(() => filtered.value.reduce((sum, item) => sum + item.points, 0));

const tableRows = computed(() => {
  const points = series.value?.points || [];
  return points.map((point, index) => ({
    ...point,
    delta: index && point.value !== null && points[index - 1].value !== null
      ? point.value - points[index - 1].value
      : null,
  })).slice().reverse();
});

const statCells = computed(() => {
  const stats = series.value?.stats;
  if (!stats) return [];
  const pct = stats.change_pct;
  const tone = pct === null || pct === undefined ? '' : pct >= 0 ? 'up' : 'down';
  return [
    { label: '最新值', value: formatNumber(stats.last_value) },
    { label: '最新日期', value: stats.last_date || '—' },
    { label: '区间涨跌', value: pct === null || pct === undefined ? '—' : `${pct >= 0 ? '+' : ''}${pct}%`, tone },
    { label: '均值', value: formatNumber(stats.avg_value) },
    { label: '最高', value: formatNumber(stats.max_value) },
    { label: '最低', value: formatNumber(stats.min_value) },
  ];
});

const chart = computed(() => {
  const points = (series.value?.points || []).filter(p => p.value !== null);
  if (points.length < 2) return null;
  const w = 720;
  const h = 180;
  const padX = 6;
  const padY = 14;
  const values = points.map(p => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || Math.abs(max) || 1;
  const step = (w - padX * 2) / (points.length - 1);
  const coords = points.map((point, index) => ({
    date: point.date,
    value: point.value,
    x: padX + step * index,
    y: padY + (h - padY * 2) * (1 - (point.value - min) / span),
  }));
  const line = coords.map((c, i) => `${i ? 'L' : 'M'}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
  return {
    w, h, points: coords,
    line,
    area: `${line} L${coords[coords.length - 1].x.toFixed(1)},${h} L${coords[0].x.toFixed(1)},${h} Z`,
    ticks: [0.25, 0.5, 0.75].map(ratio => ({ y: padY + (h - padY * 2) * ratio })),
    min: formatNumber(min),
    max: formatNumber(max),
    first: coords[0].date,
    last: coords[coords.length - 1].date,
  };
});

function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const abs = Math.abs(value);
  const digits = abs >= 1000 ? 0 : abs >= 10 ? 2 : 4;
  return Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 0, maximumFractionDigits: digits,
  });
}

function isActive(item) {
  return current.value?.source === item.source && current.value?.indicator === item.indicator;
}

async function load() {
  loading.value = true;
  try {
    const result = await api('data/indicators');
    indicators.value = (result.indicators || []).map(item => ({
      ...item,
      source_key: (result.sources || []).find(s => s.name === item.source || s.key === item.source)?.key || '',
      metric_label: METRIC_LABELS[item.metric] || '',
    }));
    sources.value = result.sources || [];
    selectedSources.value = selectedSources.value.filter(key => sources.value.some(item => item.key === key));
    if (current.value) {
      const still = indicators.value.find(isActive);
      if (still) current.value = still;
      else if (indicators.value.length) select(indicators.value[0]);
      else { current.value = null; series.value = null; }
    } else if (indicators.value.length) {
      select(indicators.value[0]);
    }
  } catch (error) {
    ElMessage.error(error.message || '读取指标目录失败');
  } finally {
    loading.value = false;
  }
}

function select(item) {
  series.value = null;
  current.value = item;
  range.value = null;
  loadSeries();
}

let seriesRequest = 0;
async function loadSeries() {
  const requestId = ++seriesRequest;
  if (!current.value) return;
  const requested = current.value;
  seriesLoading.value = true;
  try {
    const query = new URLSearchParams({
      source: current.value.source,
      indicator: current.value.indicator,
    });
    if (range.value?.[0]) query.set('start', range.value[0]);
    if (range.value?.[1]) query.set('end', range.value[1]);
    const result = await api(`data/series?${query.toString()}`);
    if (requestId === seriesRequest && current.value === requested) series.value = result;
  } catch (error) {
    if (requestId === seriesRequest && current.value === requested) {
      series.value = null;
      ElMessage.error(error.message || '读取指标序列失败');
    }
  } finally {
    if (requestId === seriesRequest) seriesLoading.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.source-label { color: #64748b; font-size: 13px; }
.source-select { width: 260px; max-width: 100%; }
.indicator-search { width: 300px; max-width: 100%; }
.result-summary { margin-left: auto; }
@media (max-width: 640px) { .result-summary { width: 100%; margin-left: 0; } }
</style>
