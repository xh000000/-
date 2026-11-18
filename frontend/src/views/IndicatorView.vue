<template>
  <div>
    <PageHead
      title="指标查询"
      description="按来源与名称检索已入库的指标，查看区间统计、走势与逐日明细；数据来自「手工数据录入」的同步结果。"
    >
      <el-button :loading="loading" @click="load">刷新</el-button>
    </PageHead>

    <div class="panel ind-filter">
      <div class="row">
        <el-radio-group v-model="source">
          <el-radio-button label="">全部来源</el-radio-button>
          <el-radio-button v-for="item in sources" :key="item.key" :label="item.key">
            {{ item.name }}
          </el-radio-button>
        </el-radio-group>
        <el-input
          v-model="keyword"
          placeholder="搜索指标名，如 螺纹钢 / 南华"
          clearable
          style="width: 240px"
        />
        <span class="tiny" style="margin-left: auto">
          {{ filtered.length }} 个指标 · {{ totalPoints }} 个数据点
        </span>
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
            {{ indicators.length ? '没有匹配的指标，换个关键字试试' : '还没有入库数据，先去「手工数据录入」同步一次' }}
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
                  <stop offset="0%" stop-color="#409eff" stop-opacity="0.22" />
                  <stop offset="100%" stop-color="#409eff" stop-opacity="0" />
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
                stroke="#409eff"
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
            {{ indicators.length ? '没有匹配的指标，清空关键字或切换来源后再看' : '还没有入库数据，先去「手工数据录入」同步一次' }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import PageHead from '../components/PageHead.vue';
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
const source = ref('');
const keyword = ref('');
const current = ref(null);
const series = ref(null);
const range = ref(null);

const gradientId = GRADIENT_ID;

const filtered = computed(() => {
  const word = keyword.value.trim();
  return indicators.value.filter(item => {
    if (source.value && item.source_key !== source.value) return false;
    if (word && !item.indicator.includes(word)) return false;
    return true;
  });
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
  current.value = item;
  range.value = null;
  loadSeries();
}

async function loadSeries() {
  if (!current.value) return;
  seriesLoading.value = true;
  try {
    const query = new URLSearchParams({
      source: current.value.source,
      indicator: current.value.indicator,
    });
    if (range.value?.[0]) query.set('start', range.value[0]);
    if (range.value?.[1]) query.set('end', range.value[1]);
    series.value = await api(`data/series?${query.toString()}`);
  } catch (error) {
    series.value = null;
    ElMessage.error(error.message || '读取指标序列失败');
  } finally {
    seriesLoading.value = false;
  }
}

onMounted(load);
</script>
