<template>
  <el-table
    :data="rows"
    class="report-list"
    border
    size="default"
    :empty-text="emptyText"
    row-key="id"
    :header-cell-style="{ background: '#f5f7fa', color: '#606266', fontWeight: '500' }"
  >
    <el-table-column label="报告标题" min-width="170">
      <template #default="{ row }">
        <button class="title-link" :title="row.title" @click="$emit('open', row.id)">{{ row.title }}</button>
        <el-tag v-if="row.raw.ai_draft" size="small" type="warning" effect="plain" style="margin-left: 6px">AI 初稿</el-tag>
        <el-popover v-if="row.aiSummary" placement="left-start" :width="380" trigger="click">
          <template #reference>
            <el-button link type="primary" size="small" style="margin-left: 6px">AI 秒读</el-button>
          </template>
          <div class="ai-summary-pop">
            <p class="as-label">核心观点</p>
            <p class="as-core">{{ row.aiSummary.core }}</p>
            <template v-if="row.aiSummary.logic">
              <p class="as-label">逻辑链</p>
              <p class="as-text">{{ row.aiSummary.logic }}</p>
            </template>
            <template v-if="row.aiSummary.data?.length">
              <p class="as-label">数据要点</p>
              <ul class="as-data">
                <li v-for="(item, index) in row.aiSummary.data" :key="index">{{ item }}</li>
              </ul>
            </template>
            <p class="as-at">AI 生成 · {{ localTime(row.aiSummary.at) }} · 仅供预览，以报告正文为准</p>
          </div>
        </el-popover>
        <el-button v-else-if="canGenerate" link type="warning" size="small" style="margin-left: 6px"
                   :loading="summaryBusy === row.id" @click="makeSummary(row)">生成秒读</el-button>
      </template>
    </el-table-column>
    <el-table-column v-if="!compact" label="摘要" min-width="104" show-overflow-tooltip>
      <template #default="{ row }">{{ row.summary || '—' }}</template>
    </el-table-column>
    <el-table-column label="分类" width="96" show-overflow-tooltip>
      <template #default="{ row }">{{ row.category }}</template>
    </el-table-column>
    <el-table-column label="创建人" width="72" show-overflow-tooltip>
      <template #default="{ row }">{{ row.author_name }}</template>
    </el-table-column>
    <el-table-column label="更新人" width="72" show-overflow-tooltip>
      <template #default="{ row }">{{ row.updated_by || row.author_name }}</template>
    </el-table-column>
    <el-table-column label="报告状态" width="88" align="center">
      <template #default="{ row }">
        <StatusTag :report="row.raw" />
      </template>
    </el-table-column>
    <el-table-column label="发布 / 审批时间" width="136">
      <template #default="{ row }">{{ row.publishAt }}</template>
    </el-table-column>
    <el-table-column label="更新时间" width="136">
      <template #default="{ row }">{{ row.updatedAt }}</template>
    </el-table-column>
    <el-table-column v-if="!narrow" label="期数" width="78" align="center">
      <template #default="{ row }">第{{ row.issue }}期</template>
    </el-table-column>
    <el-table-column v-if="!narrow" label="PV" width="50" align="center" prop="views" />
    <el-table-column label="操作" width="92" fixed="right">
      <template #default="{ row }">
        <div class="cell-actions">
          <el-button link type="primary" size="small" @click="$emit('open', row.id)">
            {{ row.editable ? '编辑' : '查看' }}
          </el-button>
          <el-button link size="small" @click="$emit('more', row.id)">更多</el-button>
        </div>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import StatusTag from './StatusTag.vue';
import { api } from '../api';
import { localTime, parseJSON } from '../utils/format';
import { refresh, user } from '../store/session';

const props = defineProps({
  reports: { type: Array, default: () => [] },
  emptyText: { type: String, default: '暂无研报' },
});
defineEmits(['open', 'more']);

/* 窄屏收起次要列：<1400 隐藏摘要，<1200 再收起期数与 PV，避免出现横向滚动条。 */
const compact = ref(false);
const narrow = ref(false);
const measure = () => {
  const width = window.innerWidth;
  compact.value = width < 1400;
  narrow.value = width < 1200;
};
onMounted(() => {
  measure();
  window.addEventListener('resize', measure);
});
onBeforeUnmount(() => window.removeEventListener('resize', measure));

const canGenerate = computed(() => ['admin', 'researcher'].includes(user.value.role));
const summaryBusy = ref(null);

async function makeSummary(row) {
  summaryBusy.value = row.id;
  try {
    await api('agent/summary', { id: row.id });
    await refresh();
    ElMessage.success('AI 秒读摘要已生成');
  } catch (error) {
    ElMessage.error(error.message || '摘要生成失败');
  } finally {
    summaryBusy.value = null;
  }
}

const rows = computed(() =>
  props.reports.map(report => {
    const meta = parseJSON(report.metadata, null);
    const cfg = parseJSON(report.config_snapshot, null);
    return {
      ...report,
      raw: report,
      summary: meta?.summary || '',
      // AI 三段式摘要卡（核心观点/逻辑链/数据要点），由「AI 秒读」入口生成
      aiSummary: parseJSON(report.ai_summary, null),
      // 分类快照存的是「一级 / 末级」全路径，列表里只显示末级，避免列宽被路径吃掉
      category: String(cfg?.category_name || report.kind || '').split('/').pop().trim(),
      publishAt: localTime(report.published_at || report.approved_at),
      updatedAt: localTime(report.updated),
      issue: report.issue || 1,
      views: report.views || 0,
      editable: report.author === user.value.id && ['草稿', '已退回'].includes(report.status),
    };
  })
);
</script>

<style scoped>
.ai-summary-pop { margin: -8px -4px; }
.as-label { margin: 8px 0 3px; color: #909399; font-size: 12px; font-weight: 600; }
.as-label:first-child { margin-top: 0; }
.as-core { margin: 0; color: #1f2937; font-size: 13px; font-weight: 600; line-height: 1.6; }
.as-text { margin: 0; color: #475569; font-size: 12px; line-height: 1.7; }
.as-data { margin: 4px 0 0 16px; padding: 0; color: #475569; font-size: 12px; line-height: 1.8; }
.as-at { margin: 10px 0 0; color: #b0b6bf; font-size: 11px; }
</style>
