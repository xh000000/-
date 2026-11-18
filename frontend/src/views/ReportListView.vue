<template>
  <div>
    <PageHead title="研报中心" description="按「我的 / 共享 / 公共」查看研报；状态口径为待提交 → 待审批 → 已通过 → 已发布，驳回后回到可编辑状态。">
      <el-button type="primary" :disabled="!canCreate" @click="dialogVisible = true">添加研报</el-button>
    </PageHead>

    <div class="filter-bar">
      <el-input v-model="filters.search" placeholder="搜索标题 / 创建人" clearable />
      <el-select v-model="filters.category" placeholder="类型筛选" clearable>
        <el-option v-for="item in leafCategories" :key="item.id" :label="item.name" :value="String(item.id)" />
      </el-select>
      <el-select v-model="filters.status" placeholder="状态筛选" clearable>
        <el-option v-for="item in statusOptions" :key="item" :label="item" :value="item" />
      </el-select>
      <el-select v-model="filters.dateKind" style="width: 108px">
        <el-option label="发布时间" value="published_at" />
        <el-option label="更新时间" value="updated" />
        <el-option label="创建时间" value="report_date" />
      </el-select>
      <el-date-picker v-model="filters.from" type="date" value-format="YYYY-MM-DD" placeholder="开始日期" />
      <span class="to">至</span>
      <el-date-picker v-model="filters.to" type="date" value-format="YYYY-MM-DD" placeholder="结束日期" />
      <el-select v-model="filters.sort" style="width: 116px">
        <el-option label="状态优先" value="status" />
        <el-option label="更新时间降序" value="updated" />
        <el-option label="标题排序" value="title" />
      </el-select>
      <el-button link @click="resetFilters">重置</el-button>
    </div>

    <div class="panel">
      <el-tabs v-model="filters.scope" class="list-tabs">
        <el-tab-pane label="我的研报" name="mine" />
        <el-tab-pane label="共享研报" name="shared" />
        <el-tab-pane label="公共研报" name="public" />
      </el-tabs>
      <ReportTable :reports="list" @open="openReport" @more="openMore" />
    </div>

    <NewReportDialog v-model="dialogVisible" @created="openReport" />
    <ReportActionDialog v-model="moreVisible" :report-id="moreId" @open="openReport" />
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import PageHead from '../components/PageHead.vue';
import ReportTable from '../components/ReportTable.vue';
import NewReportDialog from '../components/NewReportDialog.vue';
import ReportActionDialog from '../components/ReportActionDialog.vue';
import { categories, categoryTree, reports, user } from '../store/session';
import { dateOnly, parseJSON, sortReports, statusText } from '../utils/format';

const router = useRouter();
const dialogVisible = ref(false);
const moreVisible = ref(false);
const moreId = ref(null);

const statusOptions = ['待提交', '待审批', '已驳回', '已通过', '已发布'];

const filters = reactive({
  scope: 'mine',
  search: '',
  category: '',
  status: '',
  dateKind: 'published_at',
  from: '',
  to: '',
  sort: 'status',
});

const canCreate = computed(() => ['admin', 'researcher'].includes(user.value.role));

const leafCategories = computed(() =>
  categories.value.filter(item => {
    const node = categoryTree.value.find(entry => entry.id === item.id);
    return node && !node.folder && node.effective_enabled;
  })
);

const list = computed(() => {
  const me = user.value;
  const keyword = filters.search.trim().toLowerCase();
  const result = reports.value.filter(report => {
    const meta = parseJSON(report.metadata, null);
    const scopeOk = filters.scope === 'public'
      ? report.status === '已发布'
      : filters.scope === 'shared'
        ? Boolean(meta && meta.collaboration === 'shared' &&
            (me.role === 'admin' || report.author === me.id || (meta.collaborators || []).includes(me.id)))
        : (me.role === 'admin' || report.author === me.id) && (!meta || meta.collaboration === 'personal');
    const date = filters.dateKind === 'report_date'
      ? dateOnly(meta?.report_date)
      : dateOnly(report[filters.dateKind]);
    return scopeOk
      && (!filters.category || report.category_id === Number(filters.category))
      && (!filters.status || statusText(report) === filters.status)
      && (!filters.from || date >= filters.from)
      && (!filters.to || date <= filters.to)
      && `${report.title} ${report.author_name}`.toLowerCase().includes(keyword);
  });
  if (filters.sort === 'title') return result.sort((a, b) => a.title.localeCompare(b.title, 'zh'));
  if (filters.sort === 'updated') return result.sort((a, b) => String(b.updated).localeCompare(String(a.updated)));
  return sortReports(result);
});

function resetFilters() {
  filters.search = '';
  filters.category = '';
  filters.status = '';
  filters.dateKind = 'published_at';
  filters.from = '';
  filters.to = '';
  filters.sort = 'status';
}

const openReport = id => router.push({ name: 'editor', params: { id } });

function openMore(id) {
  moreId.value = id;
  moreVisible.value = true;
}
</script>
