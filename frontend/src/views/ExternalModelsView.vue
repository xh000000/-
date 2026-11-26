<template>
  <div>
    <PageHead title="外部模型" description="集中管理不同服务商和模型；每份配置独立保存密钥，按需切换。">
      <el-button :loading="loading" :disabled="!!busyId" @click="load">刷新</el-button>
      <el-button type="primary" :disabled="loading || !!busyId" @click="openEditor(null)">添加模型配置</el-button>
    </PageHead>

    <el-alert class="billing-note" type="info" :closable="false" title="外部模型通过 API 调用，费用与 ChatGPT 等聊天会员订阅分开。保存配置后，请测试接口与模型。" show-icon />
    <div class="panel active-model">
      <div>
        <span class="caption">当前启用配置</span>
        <h3>{{ config?.active_profile_name || '原有配置' }} <el-tag size="small" :type="ready ? 'success' : 'warning'">{{ ready ? '已配置，未验证' : '待完善' }}</el-tag></h3>
        <p><b>{{ config?.model || (config?.provider === 'codebuddy-cli' ? 'CLI 默认模型' : '尚未选择模型') }}</b></p>
        <p class="caption active-address">{{ config?.provider === 'codebuddy-cli' ? '本机 CLI 通道' : config?.base_url || '—' }}</p>
        <p v-if="config?.max_tokens" class="caption">单次输出上限 {{ config.max_tokens.toLocaleString() }} tokens</p>
      </div>
      <p class="caption active-description">研报中的「AI 生成本章候选」使用此配置。<br />切换后用于下一次生成，已保存的研报内容不变。</p>
    </div>

    <div class="panel">
      <div class="panel-header"><h3>模型配置</h3><span class="caption">保存后可手动启用；连接状态请点击“测试”验证</span></div>
      <div class="model-tools">
        <el-input v-model="search" clearable placeholder="搜索配置名称、模型或接口地址" aria-label="搜索模型配置" />
        <el-select v-model="providerFilter" placeholder="全部服务商" aria-label="筛选服务商"><el-option label="全部服务商" value="" /><el-option v-for="name in providerOptions" :key="name" :label="name" :value="name" /></el-select>
        <span class="caption">共 {{ filteredProfiles.length }} / {{ profiles.length }} 份配置</span>
      </div>
      <el-table v-loading="loading" :data="filteredProfiles" :empty-text="search || providerFilter ? '没有匹配的模型配置' : '暂无模型配置，点击右上角添加'">
        <el-table-column label="配置名称" min-width="160"><template #default="{ row }"><b>{{ row.name }}</b></template></el-table-column>
        <el-table-column label="服务商" width="130"><template #default="{ row }">{{ providerName(row) }}</template></el-table-column>
        <el-table-column label="模型" min-width="180" show-overflow-tooltip><template #default="{ row }">{{ row.model || (row.provider === 'codebuddy-cli' ? 'CLI 默认模型' : '未填写') }}</template></el-table-column>
        <el-table-column label="接口地址" min-width="230" show-overflow-tooltip><template #default="{ row }">{{ row.provider === 'codebuddy-cli' ? '本机 CLI 通道' : row.base_url }}</template></el-table-column>
        <el-table-column label="密钥" min-width="130"><template #default="{ row }"><span class="caption">{{ row.key_masked || '未配置' }}</span></template></el-table-column>
        <el-table-column label="启用状态" width="105"><template #default="{ row }"><el-tag v-if="row.id === activeId" type="success" size="small">当前启用</el-tag><span v-else class="caption">未启用</span></template></el-table-column>
        <el-table-column label="最近测试" min-width="190"><template #default="{ row }"><template v-if="checks[row.id]"><el-tag size="small" :type="checks[row.id].ok ? 'success' : 'danger'">{{ checks[row.id].ok ? '测试通过' : '测试失败' }}</el-tag><p class="caption test-detail">{{ checks[row.id].ok ? checks[row.id].message : explainError(checks[row.id].message) }}</p></template><span v-else class="caption">未测试</span></template></el-table-column>
        <el-table-column label="操作" width="290" fixed="right">
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
      <p class="caption list-note">“原有配置”保留原先保存的设置及环境默认值。密钥仅在服务端保存，页面只显示掩码。</p>
    </div>

    <el-dialog v-model="editorVisible" :title="form.id ? '编辑模型配置' : '添加模型配置'" width="640px" :close-on-click-modal="false">
      <el-form label-width="90px" @submit.prevent>
        <el-form-item label="服务商"><el-select :model-value="providerName(form)" :disabled="form.provider === 'codebuddy-cli'" @change="chooseProvider" style="width:100%"><el-option v-for="preset in PRESETS" :key="preset.label" :label="preset.label" :value="preset.label" /><el-option label="自定义兼容接口" value="自定义兼容接口" /></el-select></el-form-item>
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
            <p class="caption" style="margin-top: 6px">{{ addressChanged ? '接口地址已修改，请重新填写密钥，避免使用其他接口的凭据。' : '密钥只保存到当前配置，不会显示明文。' }}</p>
          </div>
        </el-form-item>
        <el-form-item label="模型名称" :required="form.provider !== 'codebuddy-cli'">
          <div class="full-width">
            <el-select v-model="form.model" filterable allow-create default-first-option clearable placeholder="测试读取模型列表，或直接输入模型名称" style="width: 100%"><el-option v-for="model in models" :key="model" :label="model" :value="model" /></el-select>
            <p class="caption" style="margin-top: 6px">{{ form.provider === 'codebuddy-cli' ? '原有 CLI 通道可留空，使用其默认模型。' : '填写服务商给出的完整模型 ID，不能只填 gpt。支持兼容 /chat/completions 的接口。' }}</p>
          </div>
        </el-form-item>
      </el-form>
      <p v-if="formResult && !formResult.ok" class="error-help">{{ explainError(formResult.message) }}</p>
      <el-alert v-if="formResult" :type="formResult.ok ? 'success' : 'error'" :title="formResult.message" show-icon :closable="false" />
      <p class="caption list-note">{{ form.id === activeId ? '此配置正在启用，保存修改后会用于下一次 AI 生成。' : '保存后加入列表；点击“启用”后才会用于研报生成。' }}</p>
      <template #footer>
        <el-button :loading="testingId === 'form'" :disabled="saving || form.provider === 'codebuddy-cli'" @click="testForm">测试连接</el-button>
        <el-button :disabled="saving" @click="editorVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="testingId === 'form'" @click="save">{{ form.id === activeId ? '保存并更新启用配置' : '保存配置' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import PageHead from '../components/PageHead.vue';
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
const form = reactive({ id: '', name: '', provider: 'openai', model: '', base_url: '', original_base: '', api_key: '', key_set: false, key_masked: '' });
const activeId = computed(() => config.value?.active_profile_id || 'legacy');
const profiles = computed(() => config.value?.profiles || (config.value ? [{ ...config.value, id: 'legacy', name: '原有配置' }] : []));
const complete = row => row.key_set && (row.model || row.provider === 'codebuddy-cli');
const ready = computed(() => complete(config.value || {}));
const addressChanged = computed(() => !!form.id && form.base_url.trim().replace(/\/+$/, '') !== form.original_base);
let formEpoch = 0;
watch(() => [form.base_url, form.model, form.api_key], () => { formEpoch++; formResult.value = null; });
watch(() => [form.base_url, form.api_key], () => { models.value = []; });
async function load() {
  loading.value = true;
  try { config.value = await api('ai/config'); }
  catch (error) { ElMessage.error(error.message || '读取模型配置失败'); }
  finally { loading.value = false; }
}
function openEditor(row) {
  Object.assign(form, { id: row?.id || '', name: row?.name || '', provider: row?.provider || 'openai', model: row?.model || '', base_url: row?.base_url || '', original_base: row?.base_url || '', api_key: '', key_set: !!row?.key_set, key_masked: row?.key_masked || '' });
  formEpoch++; formResult.value = null; models.value = []; editorVisible.value = true;
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
    if (epoch === formEpoch) { formResult.value = response; models.value = response.models || []; }
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
.model-tools { display:flex; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:16px; }
.model-tools > .el-input { width: min(360px, 100%); }
.model-tools > .el-select { width:180px; }
.test-detail { margin:6px 0 0; line-height:1.5; }
.error-help { color:var(--el-color-danger); line-height:1.7; }
.active-model { display: flex; align-items: center; justify-content: space-between; gap: 24px; border-left: 3px solid var(--el-color-primary); }
.active-model h3 { margin: 8px 0; display: flex; align-items: center; gap: 10px; }
.active-model p { margin: 7px 0 0; }
.active-address { overflow-wrap: anywhere; }
.active-description { line-height: 1.9; }
.result-note { margin-top: 18px; }
.list-note { margin-top: 14px; line-height: 1.8; }
.full-width { width: 100%; }
.model-presets { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.model-presets button { border: 0; padding: 3px 8px; border-radius: 4px; color: var(--el-color-primary); background: var(--el-color-primary-light-9); font: inherit; font-size: 12px; cursor: pointer; }
@media (max-width: 800px) { .active-model { align-items: flex-start; flex-direction: column; gap: 8px; } :deep(.el-dialog) { max-width: calc(100vw - 24px); } }
</style>
