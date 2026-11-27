<template>
  <div>
    <PageContainer title="外部模型">
      <template #actions>
        <el-button :loading="loading" :disabled="!!busyId" @click="load">刷新</el-button>
        <el-button type="primary" :disabled="loading || !!busyId" @click="openEditor(null)">添加模型配置</el-button>
      </template>

    <div class="panel active-model">
      <div class="am-body">
        <div class="am-head">
          <span class="am-dot" :class="{ 'is-ready': ready }"></span>
          <span class="am-label">当前启用</span>
          <b class="am-name">{{ config?.active_profile_name || '原有配置' }}</b>
          <el-tag size="small" :type="activeState.type">{{ activeState.text }}</el-tag>
        </div>
        <div class="am-grid">
          <div class="am-cell">
            <span>模型</span>
            <b>{{ config?.model || (config?.provider === 'codebuddy-cli' ? 'CLI 默认模型' : '尚未选择模型') }}</b>
          </div>
          <div class="am-cell">
            <span>接口地址</span>
            <b class="am-url">{{ config?.provider === 'codebuddy-cli' ? '本机 CLI 通道' : (config?.base_url || '—') }}</b>
          </div>
          <div class="am-cell">
            <span>单次输出</span>
            <b>{{ config?.max_tokens ? config.max_tokens.toLocaleString() + ' tokens' : '未设置' }}</b>
          </div>
        </div>
      </div>
      <div class="am-side">
        <el-button
          size="small" :loading="testingId === activeId"
          :disabled="!!busyId || !activeRow || activeRow.provider === 'codebuddy-cli' || !activeRow.key_set"
          @click="testSaved(activeRow)"
        >测试连接</el-button>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header"><h3>模型配置</h3></div>
      <div class="model-tools">
        <el-input v-model="search" clearable placeholder="搜索配置名称、模型或接口地址" aria-label="搜索模型配置" />
        <el-select v-model="providerFilter" placeholder="全部服务商" aria-label="筛选服务商"><el-option label="全部服务商" value="" /><el-option v-for="name in providerOptions" :key="name" :label="name" :value="name" /></el-select>
        <span class="caption model-count">共 {{ filteredProfiles.length }} / {{ profiles.length }} 份配置</span>
      </div>
      <el-table v-loading="loading" :data="filteredProfiles" :empty-text="search || providerFilter ? '没有匹配的模型配置' : '暂无模型配置，点击右上角添加'">
        <el-table-column label="配置名称" min-width="140"><template #default="{ row }"><b>{{ row.name }}</b></template></el-table-column>
        <el-table-column label="服务商 / 模型" min-width="220" show-overflow-tooltip><template #default="{ row }"><span class="muted">{{ providerName(row) }}</span><span class="model-sep">/</span>{{ row.model || (row.provider === 'codebuddy-cli' ? 'CLI 默认模型' : '未填写') }}</template></el-table-column>
        <el-table-column label="密钥" width="140"><template #default="{ row }"><span class="caption model-key">{{ row.key_masked || '未配置' }}</span></template></el-table-column>
        <el-table-column label="启用" width="100"><template #default="{ row }"><el-tag v-if="row.id === activeId" type="success" size="small">当前启用</el-tag><span v-else class="caption">未启用</span></template></el-table-column>
        <el-table-column label="最近测试" min-width="210">
          <template #default="{ row }">
            <template v-if="checks[row.id]">
              <el-tag size="small" :type="checks[row.id].ok ? 'success' : 'danger'">{{ checks[row.id].ok ? '通过' : '失败' }}</el-tag>
              <span class="test-msg" :title="testText(row)">{{ testText(row) }}</span>
            </template>
            <span v-else class="caption">未测试</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" align="right" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.id !== activeId" link type="primary" :disabled="!!busyId || !complete(row)" :loading="busyId === row.id" @click="activate(row)">启用</el-button>
            <el-button link :disabled="!!busyId" @click="openEditor(row)">编辑</el-button>
            <el-button link :disabled="!!busyId || row.provider === 'codebuddy-cli' || !row.key_set" :loading="testingId === row.id" @click="testSaved(row)">测试</el-button>
            <el-button link :disabled="!!busyId" @click="duplicate(row)">复制</el-button>
            <el-button v-if="row.id !== 'legacy'" link type="danger" :disabled="!!busyId || row.id === activeId" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-alert v-if="result" class="result-note" :type="result.ok ? 'success' : 'error'" :title="result.message" :description="result.ms ? `耗时 ${(result.ms / 1000).toFixed(1)} 秒` : ''" show-icon @close="result = null" />
    </div>

    <el-dialog v-model="editorVisible" :title="form.id ? '编辑模型配置' : '添加模型配置'" width="640px" :close-on-click-modal="false">
      <el-form label-width="96px" @submit.prevent>
        <el-form-item label="服务商">
          <div class="full-width">
            <el-select :model-value="providerName(form)" :disabled="form.provider === 'codebuddy-cli'" @change="chooseProvider" style="width:100%">
              <el-option v-for="preset in PRESETS" :key="preset.label" :label="preset.label" :value="preset.label" />
              <el-option label="自定义兼容接口" value="自定义兼容接口" />
            </el-select>
            <div v-if="form.provider !== 'codebuddy-cli'" class="model-presets">
              <button v-for="preset in PRESETS" :key="preset.label" type="button" :title="preset.base" @click="applyPreset(preset)">{{ preset.label }}</button>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="配置名称" required><el-input v-model="form.name" maxlength="60" :disabled="form.id === 'legacy'" placeholder="例如：日常撰写 / 深度分析" /></el-form-item>
        <el-form-item label="接口地址" required>
          <div class="full-width">
            <el-input v-model="form.base_url" placeholder="https://.../v1" />

          </div>
        </el-form-item>
        <el-form-item label="API Key" :required="!form.key_set || addressChanged">
          <div class="full-width">
            <el-input v-model="form.api_key" type="password" show-password autocomplete="new-password" :placeholder="form.key_set ? `已保存 ${form.key_masked}，留空不修改` : '填写此接口的密钥'" />
            <el-button v-if="form.id === 'legacy' && form.key_set" link type="danger" :disabled="saving" @click="clearLegacyKey">清除原有保存密钥</el-button>
            <p v-if="addressChanged" class="caption" style="margin-top: 6px">接口地址已修改，请重新填写密钥，避免使用其他接口的凭据。</p>
          </div>
        </el-form-item>
        <el-form-item label="模型名称" :required="form.provider !== 'codebuddy-cli'">
          <div class="full-width">
            <el-select v-model="form.model" filterable allow-create default-first-option clearable placeholder="读取模型列表后选择，或直接输入模型 ID" style="width: 100%"><el-option v-for="model in models" :key="model" :label="model" :value="model" /></el-select>
            <div class="model-fetch">
              <el-button size="small" :loading="modelsLoading" :disabled="form.provider === 'codebuddy-cli' || !form.base_url.trim()" @click="fetchModels">获取模型列表</el-button>
              <span class="caption">{{ models.length ? `已读取 ${models.length} 个模型，可在上方搜索选择` : (form.provider === 'codebuddy-cli' ? 'CLI 通道由 codebuddy 决定模型' : '从服务商接口读取可用模型，不必手动查名字') }}</span>
            </div>
            <p class="caption" style="margin-top: 6px">{{ form.provider === 'codebuddy-cli' ? '原有 CLI 通道可留空，使用其默认模型。' : '填服务商给出的完整模型 ID（不能只填 gpt），接口需兼容 /chat/completions。' }}</p>
          </div>
        </el-form-item>
      </el-form>
      <p v-if="formResult && !formResult.ok" class="error-help">{{ explainError(formResult.message) }}</p>
      <el-alert v-if="formResult" :type="formResult.ok ? 'success' : 'error'" :title="formResult.message" show-icon :closable="false" />
      <p class="caption list-note">{{ form.id === activeId ? '此配置正在启用，保存后即用于下一次 AI 生成。' : '保存后加入列表，点「启用」才会用于研报生成。' }}</p>
      <template #footer>
        <el-button :loading="testingId === 'form'" :disabled="saving || form.provider === 'codebuddy-cli'" @click="testForm">测试连接</el-button>
        <el-button :disabled="saving" @click="editorVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="testingId === 'form'" @click="save">{{ form.id === activeId ? '保存并更新启用配置' : '保存配置' }}</el-button>
      </template>
    </el-dialog>
    </PageContainer>
  </div>
</template>
<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import PageContainer from '../components/PageContainer.vue';
import { api } from '../api';
import { refresh } from '../store/session';
const PRESETS = [
  { label: 'DeepSeek', base: 'https://api.deepseek.com/v1' },
  { label: '阿里百炼', base: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { label: 'Kimi', base: 'https://api.moonshot.cn/v1' },
  { label: '智谱 GLM', base: 'https://open.bigmodel.cn/api/paas/v4' },
  { label: 'OpenAI', base: 'https://api.openai.com/v1' },
];
const search = ref('');
const providerFilter = ref('');
const checks = reactive({});
function providerName(row) {
  if (row.provider === 'codebuddy-cli') return 'CodeBuddy CLI';
  return PRESETS.find(p => row.base_url?.replace(/\/+$/, '') === p.base)?.label || '自定义兼容接口';
}
const providerOptions = computed(() => [...new Set(profiles.value.map(providerName))]);
const filteredProfiles = computed(() => profiles.value.filter(row => (!providerFilter.value || providerName(row) === providerFilter.value) && [row.name,row.model,row.base_url,providerName(row)].join(' ').toLowerCase().includes(search.value.trim().toLowerCase())));
/* 表格里第一列已经写了配置名，测试说明再带一遍前缀就是重复 */
function testText(row) {
  const check = checks[row.id];
  if (!check) return '';
  const text = check.ok ? check.message : explainError(check.message);
  return String(text || '').replace(`${row.name}：`, '');
}
function explainError(message = '') {
  if (/insufficient_quota|credit_balance_exhausted|余额|quota|billing/i.test(message)) return 'API 余额或额度不足，请到服务商控制台检查计费；聊天会员不抵扣 API 费用。';
  if (/401|invalid_api_key|密钥无效/i.test(message)) return '密钥无效或已失效，请更新当前服务商的 API Key。';
  if (/model_not_found|模型不存在|does not exist|404/i.test(message)) return '请检查接口地址、完整模型 ID 及账号的模型权限。';
  if (/429|rate.limit/i.test(message)) return '请求频率受限，请稍后重试或检查服务商额度。';
  if (/timeout|timed out|超时|resolve|连接/i.test(message)) return '请检查服务端到接口地址的网络连接。';
  return message;
}
function chooseProvider(name) {
  const preset = PRESETS.find(p => p.label === name);
  if (preset) applyPreset(preset);
  else { form.base_url = ''; form.api_key = ''; form.model = ''; form.provider = 'openai'; }
}
function duplicate(row) {
  openEditor(null);
  Object.assign(form, { name: row.name + ' 副本', base_url: row.base_url, model: row.model, provider: row.provider });
}
const config = ref(null);
const loading = ref(true);
const busyId = ref('');
const testingId = ref('');
const editorVisible = ref(false);
const saving = ref(false);
const result = ref(null);
const formResult = ref(null);
const models = ref([]);
const modelsLoading = ref(false);
/* 同一接口读过的模型列表留在前端，再次编辑同一份配置时不用重新请求上游 */
const modelCache = new Map();
const baseKey = url => String(url || '').trim().replace(/\/+$/, '');
function rememberModels(base, list) {
  if (base && list?.length) modelCache.set(baseKey(base), [...list]);
}
const form = reactive({ id: '', name: '', provider: 'openai', model: '', base_url: '', original_base: '', api_key: '', key_set: false, key_masked: '' });
const activeId = computed(() => config.value?.active_profile_id || 'legacy');
const profiles = computed(() => config.value?.profiles || (config.value ? [{ ...config.value, id: 'legacy', name: '原有配置' }] : []));
const complete = row => row.key_set && (row.model || row.provider === 'codebuddy-cli');
const ready = computed(() => complete(config.value || {}));
/* 状态卡右侧的测试按钮要作用在当前启用那份配置上 */
const activeRow = computed(() => profiles.value.find(row => row.id === activeId.value) || null);
/* 状态标签：测过就以测试结果为准，没测过才说"已配置，未验证" */
const activeState = computed(() => {
  const check = checks[activeId.value];
  if (check) return check.ok ? { type: 'success', text: '测试通过' } : { type: 'danger', text: '测试失败' };
  return ready.value ? { type: 'info', text: '已配置，未验证' } : { type: 'warning', text: '待完善' };
});
const addressChanged = computed(() => !!form.id && form.base_url.trim().replace(/\/+$/, '') !== form.original_base);
let formEpoch = 0;
watch(() => [form.base_url, form.model, form.api_key], () => { formEpoch++; formResult.value = null; });
watch(() => [form.base_url, form.api_key], () => { models.value = []; });
async function load() {
  loading.value = true;
  try { config.value = await api('ai/config'); rememberModels(config.value?.base_url, config.value?.models); }
  catch (error) { ElMessage.error(error.message || '读取模型配置失败'); }
  finally { loading.value = false; }
}
function openEditor(row) {
  /* 打开已读过的接口时先带上已知模型，省一次往返；仍可点按钮重新读取 */
  const cached = modelCache.get(baseKey(row?.base_url))
    || (row && baseKey(row.base_url) === baseKey(config.value?.base_url) ? [...(config.value?.models || [])] : []);
  Object.assign(form, { id: row?.id || '', name: row?.name || '', provider: row?.provider || 'openai', model: row?.model || '', base_url: row?.base_url || '', original_base: row?.base_url || '', api_key: '', key_set: !!row?.key_set, key_masked: row?.key_masked || '' });
  formEpoch++; formResult.value = null; models.value = []; editorVisible.value = true;
  if (cached.length) nextTick(() => { if (!models.value.length) models.value = cached; });
}
async function fetchModels() {
  if (modelsLoading.value) return;
  const base = baseKey(form.base_url);
  if (!base) return ElMessage.warning('请先填写接口地址');
  const epoch = formEpoch;
  modelsLoading.value = true;
  try {
    const response = await api('ai/models', { profile_id: form.id, base_url: base, ...(form.api_key.trim() ? { api_key: form.api_key.trim() } : {}) });
    if (epoch !== formEpoch) return;
    models.value = response.models || [];
    if (!response.ok) return ElMessage.warning(response.message || '读取模型列表失败');
    rememberModels(base, models.value);
    ElMessage.success(response.message || `已读取 ${models.value.length} 个模型`);
  } catch (error) {
    if (epoch === formEpoch) ElMessage.error(error.message || '读取模型列表失败');
  } finally { modelsLoading.value = false; }
}
function applyPreset(preset) {
  if (form.base_url === preset.base) return;
  form.base_url = preset.base; form.model = ''; form.api_key = ''; form.provider = 'openai';
}
function payload(action, row) { return { action, id: row.id, revision: config.value.profile_revision }; }
async function activate(row) {
  if (busyId.value) return;
  busyId.value = row.id;
  try {
    await api('ai/profiles', payload('activate', row)); await load(); await refresh();
    ElMessage.success(`已启用「${row.name}」，下一次 AI 生成使用此配置`);
  } catch (error) { ElMessage.error(error.message || '启用失败'); }
  finally { busyId.value = ''; }
}
async function remove(row) {
  try { await ElMessageBox.confirm(`删除「${row.name}」？`, '删除模型配置', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }); }
  catch { return; }
  busyId.value = row.id;
  try { await api('ai/profiles', payload('delete', row)); await load(); ElMessage.success('配置已删除'); }
  catch (error) { ElMessage.error(error.message || '删除失败'); }
  finally { busyId.value = ''; }
}
async function testSaved(row) {
  if (testingId.value) return;
  testingId.value = row.id;
  try { result.value = { ...await api('ai/test', { profile_id: row.id, base_url: row.base_url, model: row.model }), name: row.name }; result.value.message = `${row.name}：${result.value.message}`; }
  catch (error) { result.value = { ok: false, message: `${row.name}：${error.message}` }; }
  finally { checks[row.id] = { ...result.value }; testingId.value = ''; }
}
async function testForm() {
  if (testingId.value) return;
  testingId.value = 'form';
  const epoch = formEpoch;
  try {
    const response = await api('ai/test', { profile_id: form.id, base_url: form.base_url, model: form.model, ...(form.api_key.trim() ? { api_key: form.api_key.trim() } : {}) });
    if (epoch === formEpoch) { formResult.value = response; models.value = response.models || []; rememberModels(form.base_url, models.value); }
  } catch (error) { if (epoch === formEpoch) formResult.value = { ok: false, message: error.message }; }
  finally { testingId.value = ''; }
}
async function clearLegacyKey() {
  try { await ElMessageBox.confirm('清除原有界面保存的密钥？如果配置了环境默认密钥，系统会继续使用环境默认值。', '清除密钥', { type: 'warning', confirmButtonText: '清除', cancelButtonText: '取消' }); }
  catch { return; }
  saving.value = true;
  try { await api('ai/config', { clear_key: true }); editorVisible.value = false; await load(); await refresh(); ElMessage.success('原有保存密钥已清除'); }
  catch (error) { ElMessage.error(error.message || '清除失败'); }
  finally { saving.value = false; }
}
async function save() {
  if (saving.value) return;
  if (!form.name.trim() || !form.base_url.trim() || (!String(form.model || '').trim() && form.provider !== 'codebuddy-cli')) return ElMessage.warning('请填写配置名称、接口地址和模型名称');
  if ((!form.key_set || addressChanged.value) && !form.api_key.trim()) return ElMessage.warning('请填写此接口的密钥');
  saving.value = true;
  try {
    const data = { model: String(form.model || '').trim(), base_url: form.base_url.trim(), ...(form.api_key.trim() ? { api_key: form.api_key.trim() } : {}) };
    if (form.id === 'legacy') await api('ai/config', data);
    else await api('ai/profiles', { ...payload('save', form), name: form.name.trim(), ...data });
    if (form.id) delete checks[form.id];
    editorVisible.value = false; await load(); await refresh(); ElMessage.success('模型配置已保存');
  } catch (error) { ElMessage.error(error.message || '保存失败'); }
  finally { saving.value = false; }
}
onMounted(load);
</script>
<style scoped>
.billing-note { margin-bottom: 16px; }
.model-tools { display:flex; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:14px; }
.model-tools > .el-input { width: min(320px, 100%); }
.model-tools > .el-select { width:170px; }
.model-count { margin-left: auto; }
.model-key { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; letter-spacing: .01em; }
/* 测试结果只占一行，长错误文案省略并挂 title，避免把行撑成两行高 */
.test-msg { display: inline-block; max-width: calc(100% - 56px); margin-left: 8px; vertical-align: middle;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: var(--ink-3); }
.error-help { color:var(--el-color-danger); line-height:1.7; }

/* 当前启用：左侧状态摘要，右侧测试入口；信息按「模型 / 接口 / 上限」三列对齐 */
.active-model { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
.am-body { min-width: 0; flex: 1; }
.am-head { display: flex; align-items: center; gap: 8px; min-width: 0; }
.am-dot { flex: none; width: 7px; height: 7px; border-radius: 50%; background: var(--el-color-warning); }
.am-dot.is-ready { background: var(--el-color-success); }
.am-label { font-size: 12px; color: var(--ink-3); }
.am-name { font-size: 14px; color: var(--ink-1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.am-grid { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1.6fr) minmax(0, .9fr); gap: 10px 24px; margin-top: 12px; }
.am-cell { min-width: 0; }
.am-cell span { display: block; font-size: 11.5px; color: var(--ink-3); margin-bottom: 3px; }
.am-cell b { display: block; font-size: 12.5px; font-weight: 500; color: var(--ink-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.am-url { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px !important; }
.am-side { flex: none; }
.result-note { margin-top: 16px; }
.list-note { margin-top: 14px; line-height: 1.8; }
.full-width { width: 100%; }
.model-presets { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.model-presets button { border: 0; padding: 3px 9px; border-radius: 4px; color: var(--el-color-primary); background: var(--el-color-primary-light-9); font: inherit; font-size: 12px; cursor: pointer; }
.model-presets button:hover { background: var(--el-color-primary-light-8); }
/* 模型名：读取按钮与说明同一行，避免占满一行只剩按钮 */
.model-fetch { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.model-fetch .caption { font-size: 12px; }
@media (max-width: 900px) {
  .active-model { flex-direction: column; gap: 12px; }
  .am-grid { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .am-side { width: 100%; }
  .am-side :deep(.el-button) { width: 100%; }
  :deep(.el-dialog) { max-width: calc(100vw - 24px); }
}
</style>
