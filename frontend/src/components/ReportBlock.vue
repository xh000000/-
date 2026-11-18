<template>
  <article
    class="rich-block"
    :class="{ 'free-element': free, half: grid && block.span === 6 }"
    :style="freeStyle"
    :data-block-id="block.id"
  >
    <div v-if="editable" class="component-top" @pointerdown="startDrag">
      <span>{{ free ? '⠿ ' : '' }}{{ block.title || typeLabel }}</span>
      <span class="tools" @pointerdown.stop>
        <el-button link size="small" @click="$emit('action', 'up')">↑</el-button>
        <el-button link size="small" @click="$emit('action', 'down')">↓</el-button>
        <el-button link size="small" @click="$emit('action', 'span')">{{ block.span === 6 ? '半宽' : '整宽' }}</el-button>
        <el-button link size="small" type="danger" @click="$emit('action', 'remove')">×</el-button>
      </span>
    </div>
    <b v-else-if="block.title">{{ block.title }}</b>

    <RichText
      v-if="block.type === 'text'"
      :html="block.html ?? plainHtml"
      :editable="editable"
      @input="value => $emit('html', value)"
    />

    <img
      v-else-if="block.type === 'image'"
      :src="fileUrl(block.asset_id)"
      :alt="block.asset_name || ''"
      style="max-width: 100%; height: auto"
    />

    <template v-else>
      <svg
        v-if="block.type === 'chart' && chart.points"
        viewBox="0 0 580 215"
        width="100%"
        role="img"
        :aria-label="block.indicator + ' 时间序列图'"
      >
        <line x1="50" y1="175" x2="530" y2="175" stroke="#dcdfe6" />
        <line x1="50" y1="40" x2="50" y2="175" stroke="#dcdfe6" />
        <text x="4" y="45" font-size="10" fill="#909399">{{ chart.high }}</text>
        <text x="4" y="178" font-size="10" fill="#909399">{{ chart.low }}</text>
        <polyline :points="chart.points" fill="none" stroke="#409EFF" stroke-width="2.5" />
        <text x="50" y="198" font-size="10" fill="#909399">{{ chart.first }}</text>
        <text x="466" y="198" font-size="10" fill="#909399">{{ chart.last }}</text>
      </svg>
      <el-table v-else-if="block.type === 'table' && block.data && block.data.length" :data="block.data.slice(-12)" size="small" border>
        <el-table-column prop="date" label="日期" width="120" />
        <el-table-column prop="value" :label="block.indicator" />
        <el-table-column prop="unit" label="单位" width="100" />
      </el-table>
      <p v-else class="empty-hint">保存后由服务端生成数据快照</p>
      <p class="data-caption">
        来源：{{ block.source }} · {{ block.indicator }} · 快照 {{ (block.data || []).length }} 条 ·
        刷新于 {{ block.refreshed_at || '待保存' }}
      </p>
    </template>
  </article>
</template>

<script setup>
import { computed } from 'vue';
import RichText from './RichText.vue';
import { fileUrl } from '../api';
import { escapeHtml } from '../utils/format';

const props = defineProps({
  block: { type: Object, required: true },
  editable: { type: Boolean, default: false },
  free: { type: Boolean, default: false },
  grid: { type: Boolean, default: false },
  index: { type: Number, default: 0 },
});
const emit = defineEmits(['action', 'html', 'move']);

const TYPE_LABEL = { text: '文字组件', chart: '指标图表', table: '数据表格', image: '图片' };
const typeLabel = computed(() => TYPE_LABEL[props.block.type] || '组件');
const plainHtml = computed(() => escapeHtml(props.block.text || '').replaceAll('\n', '<br>'));

const freeStyle = computed(() =>
  props.free
    ? {
        left: (props.block.x ?? 30) + 'px',
        top: (props.block.y ?? 70 + props.index * 230) + 'px',
        width: (props.block.width ?? 620) + 'px',
        height: (props.block.height ?? 210) + 'px',
      }
    : null
);

const chart = computed(() => {
  const rows = (props.block.data || []).slice(-60);
  if (!rows.length) return {};
  const values = rows.map(row => Number(row.value));
  let low = Math.min(...values);
  let high = Math.max(...values);
  if (low === high) {
    low -= 1;
    high += 1;
  }
  const points = rows
    .map((row, i) => `${50 + (i * 480) / Math.max(1, rows.length - 1)},${175 - ((row.value - low) / (high - low)) * 135}`)
    .join(' ');
  return {
    points,
    low: low.toFixed(2),
    high: high.toFixed(2),
    first: rows[0].date,
    last: rows[rows.length - 1].date,
  };
});

/* 自由布局拖拽：直接改 block 的坐标，父组件按响应式样式即时跟随。 */
function startDrag(event) {
  if (!props.free) return;
  if (event.target.closest('button')) return;
  const block = props.block;
  const startX = event.clientX;
  const startY = event.clientY;
  const baseX = block.x ?? 30;
  const baseY = block.y ?? 70 + props.index * 230;
  const handler = move => {
    block.x = Math.max(0, Math.min(760 - (block.width || 620), baseX + move.clientX - startX));
    block.y = Math.max(0, baseY + move.clientY - startY);
  };
  const stop = () => {
    window.removeEventListener('pointermove', handler);
    window.removeEventListener('pointerup', stop);
    emit('move');
  };
  window.addEventListener('pointermove', handler);
  window.addEventListener('pointerup', stop);
}
</script>
