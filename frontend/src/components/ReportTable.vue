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
import StatusTag from './StatusTag.vue';
import { localTime, parseJSON } from '../utils/format';
import { user } from '../store/session';

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

const rows = computed(() =>
  props.reports.map(report => {
    const meta = parseJSON(report.metadata, null);
    const cfg = parseJSON(report.config_snapshot, null);
    return {
      ...report,
      raw: report,
      summary: meta?.summary || '',
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
