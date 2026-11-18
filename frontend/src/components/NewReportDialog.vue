<template>
  <el-dialog
    v-model="visible"
    title="添加研报"
    width="760px"
    :close-on-click-modal="false"
    @open="onOpen"
  >
    <el-form ref="formRef" :model="form" label-width="96px" class="basic-form">
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

      <div v-if="sectionPreview.length" class="template-preview">
        <div class="tp-head">
          <b>章节结构</b>
          <span class="caption">按《兴业期货日度策略》合集组织，创建后按章分工</span>
        </div>
        <ul class="tp-list">
          <li
            v-for="node in sectionPreview"
            :key="node.key"
            :class="node.kind === 'group' ? 'tp-group' : 'tp-leaf'"
          >
            <template v-if="node.kind === 'group'">{{ node.text }}</template>
            <template v-else>
              <span v-if="node.label" class="tp-no">{{ node.label }}</span>
              <span v-else-if="!node.title" class="tp-no">第{{ node.index }}章</span>{{ node.title }}
              <em v-if="node.type">{{ node.type }}</em>
              <span v-if="node.codes" class="tp-codes">｜ {{ node.codes }}</span>
            </template>
          </li>
        </ul>
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
import { computed, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { api } from '../api';
import { authors, categories, categoryTree, commodities, members, refresh, reports, user } from '../store/session';
import { today, ROLE_NAMES } from '../utils/format';

const visible = defineModel({ type: Boolean, default: false });
const emit = defineEmits(['created']);

const formRef = ref(null);
const saving = ref(false);
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
    .map(name => commodities.value.find(item => item.name === name && item.enabled))
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
  members.value.filter(item => item.id !== user.value.id && ['researcher', 'admin'].includes(item.role))
);

/* 章节结构预览：一级章节与二级板块按合集层级展开，不写入正文。 */
const sectionPreview = computed(() => {
  const list = currentCategory.value?.config?.sections || [];
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
    out.push({ key: item.id, kind: 'section', index: index + 1, label: item.label || '', title: item.title || '', type: item.type || '', codes });
  });
  return out;
});

function onOpen() {
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
  if (!form.category_id) return ElMessage.warning('请选择报告分类');
  if (!form.title.trim()) return ElMessage.warning('请填写报告标题');
  if (!form.byline_id) return ElMessage.warning('请先在作者管理中添加可用署名作者');
  if (form.mode === 'inherit' && !form.inherit_id) return ElMessage.warning('该分类暂无可继承的已发布报告');
  saving.value = true;
  try {
    const result = await api('reports', {
      manual: true,
      category_id: form.category_id,
      title: form.title.trim(),
      summary: form.summary,
      byline_id: form.byline_id,
      report_date: form.report_date || today(),
      commodity: form.commodity,
      collaboration: form.collaboration,
      collaborators: form.collaboration === 'shared' ? form.collaborators : [],
      layout: form.layout,
      public: form.public,
      inherit_id: form.mode === 'inherit' ? form.inherit_id : null,
    });
    await refresh();
    visible.value = false;
    ElMessage.success('报告已创建');
    emit('created', result.id);
  } catch (error) {
    ElMessage.error(error.message || '创建失败');
  } finally {
    saving.value = false;
  }
}
</script>
