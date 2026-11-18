<template>
  <div>
    <template v-if="!draft">
      <PageHead title="研报分类树" description="最多三级。末级分类配置报告章节结构与关联审批流；上级分类用于组织目录。">
        <el-button type="primary" @click="openTreeDialog(null)">添加分类</el-button>
      </PageHead>

      <div class="panel">
        <el-table
          :data="tree"
          row-key="id"
          default-expand-all
          :tree-props="{ children: 'children' }"
          empty-text="暂无分类"
        >
          <el-table-column label="分类" min-width="240">
            <template #default="{ row }">
              <el-tag v-if="row.folder" size="small" type="info" effect="plain" disable-transitions>目录</el-tag>
              <span style="margin-left: 6px">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="层级" width="86">
            <template #default="{ row }">{{ row.depth }} 级</template>
          </el-table-column>
          <el-table-column label="状态" width="96">
            <template #default="{ row }">
              <el-tag :type="row.effective_enabled ? 'success' : 'info'" size="small" disable-transitions>
                {{ row.effective_enabled ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="关联审批流" min-width="180">
            <template #default="{ row }"><span v-if="!row.folder">{{ flows.find(flow => flow.category_ids.includes(row.id))?.name || '沿用上级或默认流程' }}</span></template>
          </el-table-column>
          <el-table-column label="排序" width="80" prop="sort_order" />
          <el-table-column label="操作" width="210">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openTreeDialog(row)">编辑分类</el-button>
              <el-button v-if="!row.folder" link type="primary" size="small" @click="startConfig(row)">章节与审批配置</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </template>

    <template v-else>
      <PageHead :title="draft.name" description="配置章节结构、版式与关联审批流；新建研报自动继承；已有草稿可在编辑器主动同步章节与审批，送审后的报告继续沿用原快照。">
        <el-button @click="draft = null">返回分类列表</el-button>
      </PageHead>

      <div class="config-grid">
        <div class="panel">
          <h3>① 基础信息</h3>
          <div class="form-row" style="margin-top: 12px">
            <el-form-item label="分类名称" label-width="86px" style="flex: 1 1 100%">
              <el-input :model-value="draft.name" readonly placeholder="名称与层级请在分类树中调整" />
            </el-form-item>
            <el-form-item label="用途说明" label-width="86px" style="flex: 1 1 100%">
              <el-input v-model="draft.config.description" />
            </el-form-item>
            <el-form-item label="报告类型" label-width="86px">
              <el-input v-model="draft.config.kind" />
            </el-form-item>
            <el-form-item label="启用" label-width="60px">
              <el-switch v-model="draft.enabled" />
            </el-form-item>
            <el-form-item label="可选品种" label-width="86px" style="flex: 1 1 100%">
              <el-input v-model="commoditiesText" placeholder="用逗号分隔，如：螺纹钢，热卷" />
            </el-form-item>
            <el-form-item label="标题规则" label-width="86px" style="flex: 1 1 100%">
              <el-input v-model="draft.config.title_pattern" />
            </el-form-item>
          </div>
          <p class="caption">标题规则支持 {品种}、{类型}、{日期}（YYYY-MM-DD）与 {日期点分}（YYYY.MM.DD），研究员创建时可修改标题。</p>
        </div>

        <div class="panel">
          <h3>② 版式与品牌</h3>
          <div class="form-row" style="margin-top: 12px">
            <el-form-item label="默认布局" label-width="86px">
              <el-select v-model="draft.config.layout" style="width: 100%">
                <el-option label="常规单栏" value="flow" />
                <el-option label="智能分栏" value="grid" />
              </el-select>
            </el-form-item>
            <el-form-item label="主题色" label-width="72px">
              <el-color-picker v-model="draft.config.color" />
            </el-form-item>
            <el-form-item label="正文字号" label-width="86px">
              <el-input-number v-model="draft.config.font_size" :min="12" :max="24" controls-position="right" style="width: 100%" />
            </el-form-item>
            <el-form-item label="版头文字" label-width="86px" style="flex: 1 1 100%">
              <el-input v-model="draft.config.header" />
            </el-form-item>
            <el-form-item label="作者承诺" label-width="86px" style="flex: 1 1 100%">
              <el-input v-model="draft.config.promise" type="textarea" :rows="3" placeholder="打印尾页「作者承诺」色带下的段落" />
            </el-form-item>
            <el-form-item label="免责声明" label-width="86px" style="flex: 1 1 100%">
              <el-input v-model="draft.config.footer" type="textarea" :rows="4" />
            </el-form-item>
            <el-form-item label="联系电话" label-width="86px">
              <el-input v-model="draft.config.contact" maxlength="40" placeholder="如 021-80220262" />
            </el-form-item>
          </div>
        </div>

        <div class="panel span-2">
          <div class="panel-header">
            <h3>③ 章节结构</h3>
            <el-button size="small" @click="addSection">添加章节</el-button>
          </div>
          <div v-for="(item, index) in draft.config.sections" :key="item.id" class="config-section">
            <div class="config-section-head">
              <b>章节 {{ index + 1 }}</b>
              <span>
                <el-button link size="small" :disabled="index === 0" @click="moveSection(index, -1)">↑</el-button>
                <el-button link size="small" :disabled="index === draft.config.sections.length - 1" @click="moveSection(index, 1)">↓</el-button>
                <el-button link type="danger" size="small" :disabled="draft.config.sections.length === 1" @click="removeSection(index)">删除</el-button>
              </span>
            </div>
            <div class="form-row">
              <el-form-item label="名称" label-width="52px" style="flex: 2 1 200px">
                <el-input v-model="item.title" maxlength="100" placeholder="可留空，留空时版面只显示编号" />
              </el-form-item>
              <el-form-item label="类型" label-width="52px" style="flex: 1 1 120px">
                <el-input v-model="item.type" placeholder="如：宏观、供需" />
              </el-form-item>
              <el-form-item label="必填" label-width="52px" style="flex: 0 0 96px">
                <el-switch v-model="item.required" />
              </el-form-item>
            </div>
            <div class="form-row">
              <el-form-item label="一级章节" label-width="72px" style="flex: 2 1 220px">
                <el-input v-model="item.group" maxlength="60" placeholder="留空表示本身是一级章节，如：三、金融与商品基本面展望" />
              </el-form-item>
              <el-form-item label="编号" label-width="52px" style="flex: 1 1 130px">
                <el-input v-model="item.label" maxlength="20" placeholder="如 01、一、" />
              </el-form-item>
            </div>
            <el-form-item label="默认文字" label-width="72px">
              <el-input v-model="item.default" type="textarea" :rows="2" />
            </el-form-item>
            <el-form-item label="关联品种" label-width="72px">
              <div style="width: 100%">
                <el-select
                  v-model="item.commodity_ids"
                  multiple
                  filterable
                  clearable
                  collapse-tags
                  collapse-tags-tooltip
                  :max-collapse-tags="5"
                  placeholder="选择本章覆盖的期货品种"
                  style="width: 100%"
                >
                  <el-option-group v-for="group in commodityGroups" :key="group.id" :label="group.name">
                    <el-option
                      v-for="one in group.items"
                      :key="one.id"
                      :label="one.code ? `${one.name} ${one.code}` : one.name"
                      :value="one.id"
                    >
                      <span>{{ one.name }}</span>
                      <span class="caption" style="float: right">{{ one.code || '' }}</span>
                    </el-option>
                  </el-option-group>
                </el-select>
                <p class="caption">按板块分组选择本章覆盖的品种，新建报告时自动带到章节上；清空表示不限品种。</p>
              </div>
            </el-form-item>
          </div>
          <p v-if="!draft.config.sections.length" class="caption">至少配置一个章节</p>
        </div>

        <div class="panel span-2">
          <div class="panel-header"><h3>④ 关联审批流</h3></div>
          <el-form label-width="96px">
            <el-form-item label="审批流">
              <el-select v-model="draft.approval_flow_id" filterable placeholder="选择审批流" style="width: 100%">
                <el-option label="沿用上级或默认流程" :value="0" />
                <el-option v-for="flow in flows.filter(item => item.enabled || item.id === draft.approval_flow_id)" :key="flow.id" :label="flow.name + (flow.enabled ? '' : '（已停用，请重新选择）')" :value="flow.id" :disabled="!flow.enabled" />
              </el-select>
            </el-form-item>
          </el-form>
          <p class="caption">节点在“审批流设置”中统一维护。新研报使用关联流程；已有草稿可在编辑器同步，已送审研报保持原审批快照。</p>
        </div>
      </div>
      <div class="panel category-config-actions">
        <el-button type="primary" :loading="busy" @click="saveConfig">保存配置</el-button>
        <el-button :disabled="busy" @click="draft = null">取消</el-button>
      </div>
    </template>

    <!-- 分类编辑 -->
    <el-dialog v-model="treeVisible" :title="treeForm.id ? '编辑分类' : '新增分类'" width="480px">
      <el-form label-width="84px">
        <el-form-item label="分类名称">
          <el-input v-model="treeForm.label" maxlength="40" />
        </el-form-item>
        <el-form-item label="上级分类">
          <el-select v-model="treeForm.parent_id" clearable placeholder="无 · 一级分类" style="width: 100%">
            <el-option
              v-for="item in parentOptions"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="!treeForm.id" label="用途">
          <el-radio-group v-model="treeForm.folder">
            <el-radio :value="false">末级分类 · 用于创建报告</el-radio>
            <el-radio :value="true">目录 · 用于组织子分类</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="后台排序">
          <el-input-number v-model="treeForm.sort_order" controls-position="right" style="width: 100%" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="treeForm.enabled" />
        </el-form-item>
      </el-form>
      <p class="caption">系统会校验循环引用、三级深度与同级重名；父级停用时子级不可用于创建报告。</p>
      <template #footer>
        <el-button @click="treeVisible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="saveTree">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, reactive, ref, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { ElMessage } from 'element-plus';
import PageHead from '../components/PageHead.vue';
import { api } from '../api';
import { categories, categoryTree, commodities, refresh, flows } from '../store/session';
import { makeId } from '../utils/format';

const busy = ref(false);

/* ---------- 分类树 ---------- */
const tree = computed(() => {
  const map = new Map(categoryTree.value.map(node => [node.id, { ...node, children: [] }]));
  const roots = [];
  categoryTree.value.forEach(node => {
    const copy = map.get(node.id);
    const parent = node.parent_id ? map.get(node.parent_id) : null;
    if (parent) parent.children.push(copy);
    else roots.push(copy);
  });
  const sort = list => {
    list.sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
    list.forEach(item => sort(item.children));
  };
  sort(roots);
  return roots;
});

const treeVisible = ref(false);
const treeForm = reactive({ id: null, label: '', parent_id: null, folder: false, sort_order: 0, enabled: true });

const parentOptions = computed(() =>
  categoryTree.value.filter(node => node.id !== treeForm.id && node.depth < 3)
);

function openTreeDialog(row) {
  treeForm.id = row?.id ?? null;
  treeForm.label = row?.label || '';
  treeForm.parent_id = row?.parent_id ?? null;
  treeForm.folder = Boolean(row?.folder);
  treeForm.sort_order = row?.sort_order ?? 0;
  treeForm.enabled = row ? Boolean(row.enabled) : true;
  treeVisible.value = true;
}

async function saveTree() {
  if (!treeForm.label.trim()) return ElMessage.warning('请填写分类名称');
  busy.value = true;
  try {
    await api('category-tree', {
      id: treeForm.id,
      label: treeForm.label.trim(),
      parent_id: treeForm.parent_id ?? null,
      folder: treeForm.folder,
      sort_order: treeForm.sort_order || 0,
      enabled: treeForm.enabled,
    });
    await refresh();
    treeVisible.value = false;
    ElMessage.success('分类已保存');
  } catch (error) {
    ElMessage.error(error.message || '保存失败');
  } finally {
    busy.value = false;
  }
}

/* ---------- 分类配置 ---------- */
const draft = ref(null);

const enabledCommodities = computed(() => commodities.value.filter(item => item.enabled));
const commodityGroups = computed(() =>
  enabledCommodities.value
    .filter(item => !item.parent_id)
    .map(sector => ({ id: sector.id, name: sector.name, items: enabledCommodities.value.filter(item => item.parent_id === sector.id) }))
    .filter(group => group.items.length)
);
const commoditiesText = computed({
  get: () => (draft.value?.config.commodities || []).join('，'),
  set: value => {
    if (!draft.value) return;
    draft.value.config.commodities = String(value).split(/[，,\n]/).map(text => text.trim()).filter(Boolean);
  },
});


function startConfig(row) {
  const source = categories.value.find(item => item.id === row.id);
  if (!source) return;
  draft.value = {
    id: source.id,
    name: source.name,
    revision: source.revision,
    approval_flow_id: flows.value.find(flow => flow.category_ids.includes(source.id))?.id || 0,
    enabled: Boolean(source.enabled),
    config: JSON.parse(JSON.stringify(source.config)),
  };
  if (!draft.value.config.sections) draft.value.config.sections = [];
  if (!draft.value.config.workflow) draft.value.config.workflow = [];
}

function addSection() {
  draft.value.config.sections.push({ id: makeId(), title: '新章节', group: '', label: '', required: false, default: '', type: '', commodity_ids: [] });
}

function removeSection(index) {
  if (draft.value.config.sections.length === 1) return;
  draft.value.config.sections.splice(index, 1);
}

function moveSection(index, delta) {
  const list = draft.value.config.sections;
  const target = index + delta;
  if (target < 0 || target >= list.length) return;
  [list[index], list[target]] = [list[target], list[index]];
}

async function saveConfig() {
  const current = draft.value;
  if (!current.config.kind?.trim()) return ElMessage.warning('请填写报告类型');
  if (!current.config.sections.length) return ElMessage.warning('至少配置一个章节');
  busy.value = true;
  try {
    await api('categories', {
      id: current.id,
      revision: current.revision,
      approval_flow_id: current.approval_flow_id,
      name: current.name,
      config: current.config,
      enabled: current.enabled,
    });
    await refresh();
    draft.value = null;
    ElMessage.success('分类配置已保存');
  } catch (error) {
    ElMessage.error(error.message || '保存失败');
  } finally {
    busy.value = false;
  }
}
const route = useRoute();
onMounted(() => {
  const id = Number(route.query?.category);
  const row = categoryTree.value.find(item => item.id === id && !item.folder);
  if (row) startConfig(row);
});
</script>

<style scoped>
.category-config-actions {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
