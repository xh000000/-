<template>
  <div>
    <PageHead title="外部模型" description="保存多个模型配置，选择其中一个用于研报 AI 生成。">
      <el-button :loading="loading" :disabled="!!busyId" @click="load">刷新</el-button>
      <el-button type="primary" :disabled="loading || !!busyId" @click="openEditor(null)">添加模型配置</el-button>
    </PageHead>

    <div class="panel active-model">
      <div>
        <span class="caption">当前启用配置</span>
        <h3>{{ config?.active_profile_name || '原有配置' }} <el-tag size="small" :type="ready ? 'success' : 'warning'">{{ ready ? '配置完整' : '待完善' }}</el-tag></h3>
        <p><b>{{ config?.model || (config?.provider === 'codebuddy-cli' ? 'CLI 默认模型' : '尚未选择模型') }}</b></p>
        <p class="caption active-address">{{ config?.provider === 'codebuddy-cli' ? '本机 CLI 通道' : config?.base_url || '—' }}</p>
        <p v-if="config?.max_tokens" class="caption">单次输出上限 {{ config.max_tokens.toLocaleString() }} tokens</p>
      </div>
      <p class="caption active-description">研报中的「AI 生成本章候选」使用此配置。<br />切换后用于下一次生成，已保存的研报内容不变。</p>
    </div>

    <div class="panel">
      <div class="panel-header"><h3>模型配置</h3><span class="caption">保存后可手动启用；连接状态请点击“测试”验证</span></div>
      <el-table v-loading="loading" :data="profiles" empty-text="暂无模型配置">
        <el-table-column label="配置名称" min-width="160"><template #default="{ row }"><b>{{ row.name }}</b></template></el-table-column>
        <el-table-column label="模型" min-width="180" show-overflow-tooltip><template #default="{ row }">{{ row.model || (row.provider === 'codebuddy-cli' ? 'CLI 默认模型' : '未填写') }}</template></el-table-column>
        <el-table-column label="接口地址" min-width="230" show-overflow-tooltip><template #default="{ row }">{{ row.provider === 'codebuddy-cli' ? '本机 CLI 通道' : row.base_url }}</template></el-table-column>
        <el-table-column label="密钥" min-width="130"><template #default="{ row }"><span class="caption">{{ row.key_masked || '未配置' }}</span></template></el-table-column>
        <el-table-column label="启用状态" width="105"><template #default="{ row }"><el-tag v-if="row.id === activeId" type="success" size="small">当前启用</el-tag><span v-else class="caption">未启用</span></template></el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.id !== activeId" link type="primary" :disabled="!!busyId || !complete(row)" :loading="busyId === row.id" @click="activate(row)">启用</el-button>
            <el-button link :disabled="!!busyId" @click="openEditor(row)">编辑</el-button>
            <el-button link :disabled="!!busyId || row.provider === 'codebuddy-cli' || !row.key_set" :loading="testingId === row.id" @click="testSaved(row)">测试</el-button>
            <el-button v-if="row.id !== 'legacy'" link type="danger" :disabled="!!busyId || row.id === activeId" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-alert v-if="result" class="result-note" :type="result.ok ? 'success' : 'error'" :title="result.message" :description="result.ms ? `耗时 ${(result.ms / 1000).toFixed(1)} 秒` : ''" show-icon @close="result = null" />
      <p class="caption list-note">“原有配置”保留原先保存的设置及环境默认值。密钥仅在服务端保存，页面只显示掩码。</p>
    </div>

    <el-dialog v-model="editorVisible" :title="form.id ? '编辑模型配置' : '添加模型配置'" width="640px" :close-on-click-modal="false">
      <el-form label-width="90px" @submit.prevent>
        <el-form-item label="配置名称" required><el-input v-model="form.name" maxlength="60" :disabled="form.id === 'legacy'" placeholder="例如：日常撰写 / 深度分析" /></el-form-item>
        <el-form-item label="接口地址" required>
          <div class="full-width">
            <el-input v-model="form.base_url" placeholder="https://.../v1" />
            <div v-if="form.provider !== 'codebuddy-cli'" class="model-presets"><button v-for="preset in PRESETS" :key="preset.label" type="button" @click="applyPreset(preset)">{{ preset.label }}</button></div>
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
            <p class="caption" style="margin-top: 6px">{{ form.provider === 'codebuddy-cli' ? '原有 CLI 通道可留空，使用其默认模型。' : '填写接口要求的模型标识；支持兼容 /chat/completions 的模型服务。' }}</p>
          </div>
        </el-form-item>
      </el-form>
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
  formResult.value = null; models.value = []; editorVisible.value = true;
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
  finally { testingId.value = ''; }
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
    editorVisible.value = false; await load(); await refresh(); ElMessage.success('模型配置已保存');
  } catch (error) { ElMessage.error(error.message || '保存失败'); }
  finally { saving.value = false; }
}
onMounted(load);
</script>
<style scoped>
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
