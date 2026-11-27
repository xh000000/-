<template>
  <div>
    <PageContainer title="工作台">

    <div class="stat-grid">
      <div v-for="card in cards" :key="card.label" class="stat-card">
        <span>{{ card.label }}</span>
        <b>{{ card.value }}</b>
      </div>
    </div>

    <div class="steps">
      <span v-for="step in steps" :key="step">{{ step }}</span>
    </div>

    <div class="panel">
      <div class="panel-header">
        <h3>近期研究</h3>
        <el-button type="primary" :disabled="!canCreate" @click="dialogVisible = true">新建研报</el-button>
      </div>
      <ReportTable :reports="recent" @open="openReport" @edit="editReport" @more="moreVisible = true; moreId = $event" />
    </div>

    <NewReportDialog v-model="dialogVisible" @created="createdReport" />
    <ReportActionDialog v-model="moreVisible" :report-id="moreId" @open="openReport" @edit="editReport" />
    </PageContainer>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import { createdReportRoute } from '../utils/reportCreation';
import PageContainer from '../components/PageContainer.vue';
import ReportTable from '../components/ReportTable.vue';
import NewReportDialog from '../components/NewReportDialog.vue';
import ReportActionDialog from '../components/ReportActionDialog.vue';
import { dataRows, reports, session, user } from '../store/session';
import { sortReports } from '../utils/format';

const router = useRouter();
const createdReport = (id, options) => router.push(createdReportRoute(id, options));
const dialogVisible = ref(false);
const moreVisible = ref(false);
const moreId = ref(null);

const canCreate = computed(() => ['admin', 'researcher'].includes(user.value.role));
const steps = ['① 数据入库', '② 研究撰写', '③ 研究复核', '④ 合规审核', '⑤ 内部发布', '⑥ 知识沉淀'];

const cards = computed(() => {
  const list = reports.value;
  return [
    { label: '研究报告', value: list.length },
    { label: '审核处理中', value: list.filter(item => ['研究复核', '合规审核'].includes(item.status)).length },
    { label: '已发布', value: list.filter(item => item.status === '已发布').length },
    { label: '数据记录', value: dataRows.value.length >= 500 ? '500+' : dataRows.value.length },
  ];
});

const recent = computed(() => sortReports(reports.value).slice(0, 8));

/* 与研报中心一致：点标题进只读详情，点「编辑」才进编辑态。 */
const openReport = id => router.push({ name: 'editor', params: { id }, query: { mode: 'view' } });
const editReport = id => router.push({ name: 'editor', params: { id } });
</script>
