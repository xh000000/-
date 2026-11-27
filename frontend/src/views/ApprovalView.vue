<template>
  <div>
    <PageContainer title="审核中心">

    <div class="panel">
      <el-tabs v-model="scope" class="list-tabs">
        <el-tab-pane label="待处理" name="pending" />
        <el-tab-pane label="已处理" name="handled" />
        <el-tab-pane label="我发起的" name="initiated" />
      </el-tabs>
      <ReportTable :reports="list" empty-text="当前页签暂无研报" @open="openReport" @edit="editReport" @more="openMore" />
    </div>

    <ReportActionDialog v-model="moreVisible" :report-id="moreId" @open="openReport" @edit="editReport" />
    </PageContainer>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import PageContainer from '../components/PageContainer.vue';
import ReportTable from '../components/ReportTable.vue';
import ReportActionDialog from '../components/ReportActionDialog.vue';
import { reports, user } from '../store/session';
import { sortReports } from '../utils/format';

const router = useRouter();
const scope = ref('pending');
const moreVisible = ref(false);
const moreId = ref(null);

const list = computed(() => {
  const me = user.value;
  const filtered = reports.value.filter(report => {
    if (scope.value === 'initiated') return report.author === me.id;
    if (scope.value === 'handled') return report.handled_by_me;
    return (report.allowed_actions || []).some(action => ['通过', '退回', '发布'].includes(action));
  });
  return sortReports(filtered);
});

/* 审核也先看详情，审批动作仍在详情页顶部，不会误进编辑态。 */
const openReport = id => router.push({ name: 'editor', params: { id }, query: { mode: 'view' } });
const editReport = id => router.push({ name: 'editor', params: { id } });

function openMore(id) {
  moreId.value = id;
  moreVisible.value = true;
}
</script>
