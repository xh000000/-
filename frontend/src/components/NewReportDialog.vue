<template>
  <el-dialog
    v-model="visible"
    title="新建研报"
    width="760px"
    :close-on-click-modal="false"
    @open="onOpen"
  >
    <el-form ref="formRef" :model="form" label-width="96px" class="basic-form">
      <el-form-item label="写作方式">
        <div>
          <el-radio-group v-model="writingMode">
            <el-radio value="manual">手工编写</el-radio>
            <el-radio value="ai">AI 辅助</el-radio>
          </el-radio-group>
          <p class="caption">{{ writingMode === 'manual' ? '创建草稿后进入编辑器，自行撰写；之后也可随时使用 AI。' : form.collaboration === 'shared' ? '在下方分配章节负责人，创建后由 AI 生成候选、各负责人确认。' : '创建草稿后选择 Skill、章节和资料，由 AI 生成候选，核对后采用。' }}</p>
        </div>
      </el-form-item>

      <el-form-item label="新增方式">
        <el-radio-group v-model="form.mode" @change="onModeChange">
          <el-radio value="new">新增报告</el-radio>
          <el-radio value="inherit">继承报告</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="报告分类" required>
        <el-select v-model="form.category_id" placeholder="请选择末级分类" style="width: 100%" @change="syncCategory">
          <el-option v-for="item in leafCategories" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </el-form-item>

      <el-form-item v-if="form.mode === 'inherit'" label="继承报告">
        <el-select v-model="form.inherit_id" placeholder="选择同分类的已发布报告" style="width: 100%">
          <el-option v-for="item in inheritOptions" :key="item.id" :label="`${item.title} · v${item.version}`" :value="item.id" />
        </el-select>
      </el-form-item>

      <el-form-item label="报告标题" required>
        <el-input v-model="form.title" maxlength="200" show-word-limit placeholder="按分类标题规则自动生成，可修改" />
      </el-form-item>

      <el-form-item label="报告摘要">
        <el-input v-model="form.summary" type="textarea" :rows="2" maxlength="2000" placeholder="选填，用于列表摘要列" />
      </el-form-item>

      <el-form-item label="署名作者" required>
        <el-select v-model="form.byline_id" placeholder="请选择署名作者" style="width: 100%">
          <el-option v-for="item in bylineOptions" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </el-form-item>

      <el-form-item label="研究品种" required>
        <el-select v-model="form.commodity" placeholder="请选择品种" style="width: 100%" @change="syncTitle">
          <el-option
            v-for="item in commodityOptions"
            :key="item.name"
            :label="item.code ? `${item.name}（${item.code}）` : item.name"
            :value="item.name"
          >
            <span>{{ item.name }}</span>
            <span class="caption" style="float: right">{{ item.code || item.sector }}</span>
          </el-option>
        </el-select>
      </el-form-item>

      <el-form-item label="创建日期" required>
        <el-date-picker
          v-model="form.report_date"
          type="date"
          value-format="YYYY-MM-DD"
          style="width: 100%"
          @change="syncTitle"
        />
      </el-form-item>

      <el-form-item label="协作方式">
        <el-radio-group v-model="form.collaboration">
          <el-radio value="personal">个人</el-radio>
          <el-radio value="shared">多人协作（按章节分工）</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item v-if="form.collaboration === 'shared'" label="协作人">
        <el-select
          v-model="form.collaborators"
          multiple
          filterable
          clearable
          collapse-tags
          collapse-tags-tooltip
          :max-collapse-tags="4"
          :disabled="!collaboratorOptions.length"
          placeholder="选择参与本报告的研究员"
          style="width: 100%"
        >
          <el-option
            v-for="item in collaboratorOptions"
            :key="item.id"
            :label="item.name"
            :value="item.id"
          >
            <span>{{ item.name }}</span>
            <span class="caption" style="float: right">{{ ROLE_NAMES[item.role] || item.role }}</span>
          </el-option>
        </el-select>
        <p v-if="!collaboratorOptions.length" class="caption">请先创建研究员账号</p>
        <p v-else-if="form.collaborators.length" class="caption">
          已选 {{ form.collaborators.length }} 人，创建后在章节设置里按人分配章节
        </p>
      </el-form-item>

      <el-form-item label="报告布局">
        <el-radio-group v-model="form.layout">
          <el-radio value="flow">常规布局</el-radio>
          <el-radio value="grid">智能布局</el-radio>
          <el-radio value="free">自由布局</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="公开发布">
        <el-radio-group v-model="form.public">
          <el-radio :value="true">是 · 发布后所有人可见</el-radio>
          <el-radio :value="false">否 · 仅参与者与审批人可见</el-radio>
        </el-radio-group>
      </el-form-item>

      <div v-if="sectionPreview.length" class="template-preview creation-sections">
        <div class="tp-head"><b>{{ form.collaboration === 'shared' ? '章节结构与分工' : '章节结构' }}</b><span class="caption">{{ chapterRows.length }} 章 · {{ sectionGroups.length }} 组</span></div>
        <p class="caption">{{ form.mode === 'inherit' ? '沿用原报告结构，编辑人按本次选择重新分配。' : '沿用分类模板；只为本次研报设置编辑人，不修改分类。' }}</p>
        <div v-if="form.collaboration === 'shared'" class="creation-batch">
          <el-select v-model="batchEditors" multiple collapse-tags collapse-tags-tooltip aria-label="统一章节编辑人" placeholder="选择统一编辑人" style="width:240px"><el-option v-for="person in assignmentPeople" :key="person.id" :label="person.name" :value="person.id" /></el-select>
          <el-button :disabled="!batchEditors.length" @click="assignGroup(chapterRows)">应用全部章节</el-button>
        </div>
        <el-collapse v-model="openGroups" class="creation-outline">
          <el-collapse-item v-for="group in sectionGroups" :key="group.key" :name="group.key">
            <template #title><b>{{ group.title }}</b><span class="caption" style="margin-left:10px">{{ group.sections.length }} 章</span></template>
            <div v-if="form.collaboration === 'shared'" class="creation-group-action"><el-button link type="primary" :disabled="!batchEditors.length" @click="assignGroup(group.sections)">将统一编辑人应用本组</el-button></div>
            <el-table :data="group.sections" size="small">
              <el-table-column label="章节" min-width="150"><template #default="{row}"><span class="caption" style="margin-right:8px">{{ row.label || row.index }}</span>{{ row.title || '未命名章节' }}<div v-if="row.type" class="caption">{{ row.type }}</div></template></el-table-column>
              <el-table-column label="关联品种" min-width="120"><template #default="{row}"><span class="caption">{{ row.codes || '按研报品种' }}</span></template></el-table-column>
              <el-table-column v-if="form.collaboration === 'shared'" label="编辑人" min-width="220"><template #default="{row}"><el-select v-model="assignments[row.key]" multiple collapse-tags collapse-tags-tooltip :aria-label="`章节编辑人 ${row.title || row.key}`" placeholder="选择编辑人" style="width:100%"><el-option v-for="person in assignmentPeople" :key="person.id" :label="person.name" :value="person.id" /></el-select></template></el-table-column>
            </el-table>
          </el-collapse-item>
        </el-collapse>
        <p v-if="form.collaboration === 'shared'" class="caption">每章至少一位编辑人，可多人共同编辑。创建后仍可在「章节分工」中调整。</p>
      </div>

      <p class="caption">{{ help }}</p>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">确定并进入编辑器</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { api } from '../api';
import { authors, categories, categoryTree, commodities, members, refresh, reports, user } from '../store/session';
import { today, ROLE_NAMES } from '../utils/format';

const props = defineProps({ aiMode: {type:Boolean,default:false} });
const visible = defineModel({ type: Boolean, default: false });
const emit = defineEmits(['created']);

const formRef = ref(null);
const saving = ref(false);
const writingMode = ref('manual');
const assignments = reactive({});
const batchEditors = ref([]);
const openGroups = ref([]);
const help = ref('');
const form = reactive({
  mode: 'new',
  category_id: null,
  inherit_id: null,
  title: '',
  summary: '',
  byline_id: null,
  commodity: '',
  report_date: today(),
  collaboration: 'personal',
  collaborators: [],
  layout: 'flow',
  public: true,
});

const leafCategories = computed(() =>
  categories.value.filter(item => {
    const node = categoryTree.value.find(entry => entry.id === item.id);
    return node && !node.folder && node.effective_enabled;
  })
);

const currentCategory = computed(() => categories.value.find(item => item.id === form.category_id) || null);

const bylineOptions = computed(() => {
  const kind = currentCategory.value?.config?.kind;
  return authors.value.filter(item => {
    if (!item.enabled) return false;
    let types = [];
    try {
      types = JSON.parse(item.types || '[]');
    } catch {
      types = [];
    }
    return types.includes(kind);
  });
});

const commodityOptions = computed(() => {
  const names = currentCategory.value?.config?.commodities || [];
  return names
    .map(name => commodities.value.find(item => item.name === name && item.enabled && (!item.parent_id || commodities.value.some(parent => parent.id === item.parent_id && parent.enabled))))
    .filter(Boolean)
    .map(item => ({
      name: item.name,
      code: item.code || '',
      sector: commodities.value.find(one => one.id === item.parent_id)?.name || '',
    }));
});

const inheritOptions = computed(() =>
  reports.value
    .filter(item => item.document && item.category_id === form.category_id && item.status === '已发布')
    .sort((a, b) => String(b.updated).localeCompare(String(a.updated)))
);

const collaboratorOptions = computed(() =>
  members.value.filter(item => item.id !== user.value.id && item.enabled !== 0 && ['researcher', 'admin'].includes(item.role))
);

/* 章节结构预览：一级章节与二级板块按合集层级展开，不写入正文。 */
const sectionPreview = computed(() => {
  let config = currentCategory.value?.config;
  if (form.mode === 'inherit') {
    const source = inheritOptions.value.find(item => item.id === form.inherit_id);
    try { config = JSON.parse(source?.config_snapshot || 'null') || config; } catch { /* fallback to the category */ }
  }
  let list = config?.sections || [];
  if(form.mode === 'inherit'){
    const source=inheritOptions.value.find(item=>item.id===form.inherit_id);
    try{const actual=JSON.parse(source?.document || '{}').sections;if(actual)list=actual.map(section=>({...list.find(x=>x.id===section.id),...section}));}catch{}
  }
  const out = [];
  let group = null;
  list.forEach((item, index) => {
    const current = item.group || '';
    if (current && current !== group) out.push({ key: 'g' + out.length, kind: 'group', text: current });
    group = current;
    const codes = (item.commodity_ids || [])
      .map(id => commodities.value.find(one => one.id === id))
      .filter(Boolean)
      .map(one => one.code || one.name)
      .join(' · ');
    out.push({ key: item.id, group: current, kind: 'section', index: index + 1, label: item.label || '', title: item.title || '', type: item.type || '', codes });
  });
  return out;
});

const chapterRows=computed(()=>sectionPreview.value.filter(x=>x.kind==='section'));
const sectionGroups=computed(()=>{
  const groups=[];
  for(const row of chapterRows.value){const key=row.group || '未分组章节';let group=groups.find(x=>x.key===key);if(!group){group={key,title:key,sections:[]};groups.push(group);}group.sections.push(row);}
  return groups;
});
const assignmentPeople=computed(()=>[{id:user.value.id,name:user.value.name || '我'},...collaboratorOptions.value.filter(x=>form.collaborators.includes(x.id))]);
function assignGroup(rows){for(const row of rows)assignments[row.key]=[...batchEditors.value];}
watch(()=>[form.category_id,form.mode,form.inherit_id],()=>{Object.keys(assignments).forEach(key=>delete assignments[key]);for(const row of chapterRows.value)assignments[row.key]=[user.value.id];},{flush:'sync'});
watch(()=>[chapterRows.value.map(x=>x.key).join(','),assignmentPeople.value.map(x=>x.id).join(',')],()=>{
  const allowed=new Set(assignmentPeople.value.map(x=>x.id));
  const ids=new Set(chapterRows.value.map(x=>x.key));
  for(const key of Object.keys(assignments))if(!ids.has(key))delete assignments[key];
  for(const row of chapterRows.value){const kept=(assignments[row.key] || []).filter(id=>allowed.has(id));assignments[row.key]=kept.length ? kept : [user.value.id];}
  batchEditors.value=batchEditors.value.filter(id=>allowed.has(id));
  openGroups.value=sectionGroups.value.map(x=>x.key);
},{immediate:true,flush:'sync'});

function onOpen() {
  Object.keys(assignments).forEach(key=>delete assignments[key]);batchEditors.value=[];
  writingMode.value = props.aiMode ? 'ai' : 'manual';
  form.title = '';
  form.byline_id = null;
  form.commodity = '';
  form.mode = 'new';
  form.inherit_id = null;
  form.summary = '';
  form.collaboration = 'personal';
  form.collaborators = [];
  form.layout = 'flow';
  form.public = true;
  form.report_date = today();
  form.category_id = leafCategories.value[0]?.id ?? null;
  syncCategory();
}

function onModeChange() {
  if (form.mode !== 'inherit') form.inherit_id = null;
  else if (!inheritOptions.value.some(item => item.id === form.inherit_id)) {
    form.inherit_id = inheritOptions.value[0]?.id ?? null;
  }
}

function syncTitle() {
  const category = currentCategory.value;
  if (!category) return;
  const cfg = category.config;
  const dotted = String(form.report_date || '').replaceAll('-', '.');
  form.title = String(cfg.title_pattern || '{品种}{类型}｜{日期}')
    .replaceAll('{品种}', form.commodity || '')
    .replaceAll('{类型}', cfg.kind || '')
    .replaceAll('{日期点分}', dotted)
    .replaceAll('{日期}', form.report_date || '');
}

function syncCategory() {
  const category = currentCategory.value;
  if (!category) {
    help.value = '';
    return;
  }
  const cfg = category.config;
  form.byline_id = bylineOptions.value[0]?.id ?? null;
  form.commodity = commodityOptions.value[0]?.name || '';
  form.inherit_id = inheritOptions.value[0]?.id ?? null;
  help.value = `分类可选题材品种 ${(cfg.commodities || []).length} 个；分类、新增方式、协作方式与布局创建后不可修改。`;
  if (!bylineOptions.value.length) help.value += ' 当前分类没有可用署名作者，请先在作者管理中维护。';
  syncTitle();
}

async function submit() {
  if (saving.value) return;
  if (!form.category_id) return ElMessage.warning('请选择报告分类');
  if (!form.title.trim()) return ElMessage.warning('请填写报告标题');
  if (!form.byline_id) return ElMessage.warning('请先在作者管理中添加可用署名作者');
  if (!form.commodity) return ElMessage.warning('请选择研究品种');
  if (!form.report_date) return ElMessage.warning('请选择创建日期');
  if (form.collaboration === 'shared' && !form.collaborators.length) return ElMessage.warning('请选择至少一名协作人');
  if (form.mode === 'inherit' && !inheritOptions.value.some(item => item.id === form.inherit_id)) return ElMessage.warning('该分类暂无可继承的已发布报告');
  if(form.collaboration === 'shared' && chapterRows.value.some(row=>!assignments[row.key]?.length))return ElMessage.warning('请为每个章节选择至少一位编辑人');
  saving.value = true;
  try {
    const result = await api('reports', {
      manual: true,
      category_id: form.category_id,
      title: form.title.trim(),
      summary: form.summary,
      byline_id: form.byline_id,
      report_date: form.report_date,
      commodity: form.commodity,
      collaboration: form.collaboration,
      collaborators: form.collaboration === 'shared' ? form.collaborators : [],
      layout: form.layout,
      public: form.public,
      inherit_id: form.mode === 'inherit' ? form.inherit_id : null,
      ...(form.collaboration === 'shared' ? {section_assignments:chapterRows.value.map(row=>({section_id:row.key,editors:assignments[row.key]}))} : {}),
    });
    await refresh();
    visible.value = false;
    ElMessage.success('报告已创建');
    emit('created', result.id, {writingMode: writingMode.value, collaboration: form.collaboration,...(form.collaboration === 'shared' ? {assignmentsReady:true} : {})});
  } catch (error) {
    ElMessage.error(error.message || '创建失败');
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.creation-sections{padding:16px}.creation-batch{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin:14px 0}.creation-outline{max-height:420px;overflow:auto;margin-top:12px}.creation-group-action{text-align:right;padding:0 6px 6px}.creation-sections>.caption{margin:10px 0;line-height:1.6}
</style>
