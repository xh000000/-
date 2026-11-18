<template>
  <div>
    <PageHead title="基本配置" description="外部模型与账号信息；研报审批规则在「审批流配置」与「角色管理」中维护。">
    </PageHead>

    <div class="panel">
      <div class="ai-head">
        <div>
          <h3>外部模型</h3>
          <p class="caption">
            「AI 生成本章候选」使用这里的配置。密钥只保存在服务端数据库，接口只回传掩码。
          </p>
        </div>
        <el-tag :type="aiReady ? 'success' : 'warning'" size="small" effect="light" disable-transitions>
          {{ aiReady ? '已就绪' : '未配置密钥' }}
        </el-tag>
      </div>

      <dl class="ai-facts">
        <div>
          <dt>当前模型</dt>
          <dd>
            <b class="ellipsis">{{ aiLoading ? '读取中…' : modelName }}</b>
            <el-tag v-if="modelName !== '未配置' && !aiLoading" size="small" effect="plain" disable-transitions>
              {{ modelFromEnv ? '环境变量默认' : '界面设置' }}
            </el-tag>
          </dd>
        </div>
        <div>
          <dt>接口地址</dt>
          <dd class="mono ellipsis">{{ aiConfig?.base_url || '—' }}</dd>
        </div>
        <div>
          <dt>密钥</dt>
          <dd class="mono">{{ aiConfig?.key_masked || '未配置' }}</dd>
        </div>
        <div>
          <dt>单次输出上限</dt>
          <dd>{{ aiConfig?.max_tokens ?? '—' }}<span class="tiny">tokens</span></dd>
        </div>
      </dl>

      <template v-if="isAdmin">
        <div class="ai-body">
          <div class="ai-main">
            <el-form class="ai-form" label-width="76px" label-position="left" @submit.prevent>
              <el-form-item label="接口地址">
                <div class="ai-field">
                  <el-input v-model="apiBase" placeholder="https://api.deepseek.com/v1" clearable />
                  <div class="ai-presets">
                    <span class="tiny">常用：</span>
                    <button
                      v-for="preset in PRESETS"
                      :key="preset.label"
                      type="button"
                      class="ai-preset"
                      :class="{ on: isPreset(preset) }"
                      @click="applyPreset(preset)"
                    >
                      {{ preset.label }}
                    </button>
                  </div>
                </div>
              </el-form-item>

              <el-form-item label="API Key">
                <div class="ai-field">
                  <el-input
                    v-model="apiKey"
                    type="password"
                    show-password
                    autocomplete="new-password"
                    :placeholder="aiConfig?.key_set ? `已配置 ${aiConfig.key_masked}，留空则不修改` : '填写密钥，例如 sk-...'"
                  />
                  <div class="ai-field-note">
                    <span v-if="aiConfig?.key_set">
                      当前密钥来自{{ aiConfig.key_source }}，留空保存表示继续使用
                    </span>
                    <span v-else>保存后立即生效，不会下发到浏览器</span>
                    <el-link v-if="aiConfig?.key_set" type="danger" :underline="false" @click="clearKey">
                      清除已保存的密钥
                    </el-link>
                  </div>
                </div>
              </el-form-item>

              <el-form-item label="模型">
                <div class="ai-field">
                  <el-select
                    v-model="selectedModel"
                    filterable
                    allow-create
                    default-first-option
                    clearable
                    :loading="aiTesting"
                    :placeholder="aiModels.length ? '选择模型，或直接输入模型名' : '先点「测试连接」读取列表，或直接输入模型名'"
                  >
                    <el-option v-for="name in aiModels" :key="name" :label="name" :value="name" />
                  </el-select>
                  <div class="ai-field-note">
                    <span v-if="aiModels.length">可选项 {{ aiModels.length }} 个，取自当前接口地址的 /models</span>
                    <span v-else-if="aiConfig?.note">{{ aiConfig.note }}</span>
                    <span v-else>列表为空时直接输入模型名即可，例如 deepseek-v4-pro</span>
                  </div>
                </div>
              </el-form-item>
            </el-form>

            <el-alert
              v-if="testState"
              class="ai-alert"
              :type="testState.ok ? 'success' : 'error'"
              :title="testState.message"
              :description="testState.ms ? `耗时 ${(testState.ms / 1000).toFixed(1)} 秒` : ''"
              show-icon
              @close="testState = null"
            />
          </div>

          <aside class="ai-help">
            <b>填写提示</b>
            <ul>
              <li>接口地址填到版本号为止（如 <code>/v1</code>、<code>/v4</code>），不要带 <code>/chat/completions</code>。</li>
              <li>选「常用」会自动填好地址；换服务商后先「测试连接」再选模型。</li>
              <li>密钥只写进服务端数据库，任何接口都只回传掩码。</li>
              <li>生成结果是候选草稿，采用前请人工核对。</li>
            </ul>
          </aside>
        </div>

        <div class="ai-actions">
          <el-button type="primary" :loading="aiSaving" :disabled="!dirty" @click="saveAi">保存配置</el-button>
          <el-button :loading="aiTesting" @click="testAi">测试连接</el-button>
          <el-button v-if="dirty" text @click="loadAi">放弃修改</el-button>
          <span v-if="dirty" class="ai-dirty">有未保存的修改</span>
          <span v-else class="tiny">保存后立即生效，无需重启服务</span>
        </div>
      </template>
      <p v-else class="caption">
        仅管理员可修改模型与密钥，当前使用「{{ modelName }}」{{ aiReady ? '（密钥已配置）' : '（密钥未配置）' }}。
      </p>
    </div>

    <div class="panel">
      <h3>我的账号</h3>
      <p>
        姓名：<b>{{ user.name }}</b>　角色：{{ roleName }}　部门：{{ deptName }}
      </p>
      <p class="caption">手机：{{ user.phone || '—' }}　职务：{{ user.title || '—' }}</p>
      <div class="row" style="margin-top: 14px">
        <el-button type="primary" @click="passwordVisible = true">修改密码</el-button>
      </div>
      <p class="caption" style="margin-top: 10px">
        修改密码后当前账号的全部登录会话立即失效；未勾选「保持登录」的会话 30 分钟无操作自动失效。
      </p>
    </div>

    <div class="panel">
      <h3>研报审批</h3>
      <p class="caption">
        审批流可按分类设置多节点（或签 / 会签 / 依次审批），必须包含一个合规审核节点；新建报告时按分类匹配并快照，
        未匹配的分类沿用分类自带的审批节点。作者不能审核或发布自己的报告。
      </p>
      <div class="row" style="margin-top: 14px">
        <el-button @click="router.push('/config/flows')">前往审批流配置</el-button>
        <el-button @click="router.push('/system/roles')">前往角色管理</el-button>
      </div>
    </div>

    <ChangePasswordDialog v-model="passwordVisible" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import PageHead from '../components/PageHead.vue';
import ChangePasswordDialog from '../components/ChangePasswordDialog.vue';
import { ROLE_NAMES } from '../utils/format';
import { api } from '../api';
import { isAdmin, refresh, session, user, users } from '../store/session';

const router = useRouter();
const passwordVisible = ref(false);

/* ---------- 外部模型：管理员可选模型，保存即生效 ---------- */
const PRESETS = [
  { label: 'DeepSeek', base: 'https://api.deepseek.com/v1' },
  { label: '阿里百炼', base: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { label: 'Kimi', base: 'https://api.moonshot.cn/v1' },
  { label: '智谱 GLM', base: 'https://open.bigmodel.cn/api/paas/v4' },
  { label: 'OpenAI', base: 'https://api.openai.com/v1' },
];

const aiConfig = ref(null);
const aiLoading = ref(false);
const aiSaving = ref(false);
const aiTesting = ref(false);
const selectedModel = ref('');
const apiBase = ref('');
const apiKey = ref('');
const testState = ref(null);

const aiModels = computed(() => aiConfig.value?.models || []);
const aiReady = computed(() => Boolean(aiConfig.value?.key_set ?? session.data?.ai));
const modelName = computed(() => aiConfig.value?.model || session.data?.model || '未配置');
const modelFromEnv = computed(() => aiConfig.value?.source === '环境变量' && Boolean(aiConfig.value.model));

/* 与服务端保存值比较：没有改动就没必要点亮保存按钮，也避免手滑重复提交 */
const dirty = computed(() => {
  if (!aiConfig.value) return false;
  const trim = value => String(value || '').trim().replace(/\/+$/, '');
  return (
    trim(selectedModel.value) !== trim(aiConfig.value.model) ||
    trim(apiBase.value) !== trim(aiConfig.value.base_url) ||
    Boolean(apiKey.value.trim())
  );
});

const isPreset = preset => String(apiBase.value || '').trim().replace(/\/+$/, '') === preset.base;

async function loadAi() {
  if (!isAdmin.value) return;
  aiLoading.value = true;
  try {
    aiConfig.value = await api('ai/config');
    selectedModel.value = aiConfig.value.model || '';
    apiBase.value = aiConfig.value.base_url || '';
    apiKey.value = '';
    testState.value = null;
  } catch (error) {
    ElMessage.error(error.message || '读取模型配置失败');
  } finally {
    aiLoading.value = false;
  }
}

/* 点常用服务商：换地址、清空旧模型名，有密钥就顺手试一次把模型列表拉回来 */
async function applyPreset(preset) {
  if (isPreset(preset)) return;
  apiBase.value = preset.base;
  selectedModel.value = '';
  aiConfig.value = { ...(aiConfig.value || {}), models: [] };
  testState.value = null;
  if (aiConfig.value?.key_set || apiKey.value.trim()) await testAi();
}

async function testAi() {
  aiTesting.value = true;
  testState.value = null;
  try {
    const body = { base_url: apiBase.value, model: selectedModel.value };
    if (apiKey.value.trim()) body.api_key = apiKey.value.trim();
    const result = await api('ai/test', body);
    testState.value = result;
    if (result.models?.length) {
      aiConfig.value = { ...(aiConfig.value || {}), models: result.models };
    }
  } catch (error) {
    testState.value = { ok: false, message: error.message || '测试失败', ms: 0 };
  } finally {
    aiTesting.value = false;
  }
}

async function saveAi() {
  aiSaving.value = true;
  try {
    const payload = { model: selectedModel.value || '', base_url: apiBase.value || '' };
    const newKey = apiKey.value.trim();
    if (newKey) payload.api_key = newKey;
    await api('ai/config', payload);
    ElMessage.success(newKey ? '配置已保存，密钥已更新' : '配置已保存');
    await Promise.all([loadAi(), refresh()]);
  } catch (error) {
    ElMessage.error(error.message || '保存模型配置失败');
  } finally {
    aiSaving.value = false;
  }
}

async function clearKey() {
  try {
    await ElMessageBox.confirm('清除后回落到环境变量里的密钥；若环境变量也没配，AI 生成将不可用。', '清除密钥？', {
      confirmButtonText: '清除', cancelButtonText: '取消', type: 'warning',
    });
  } catch {
    return;
  }
  aiSaving.value = true;
  try {
    const result = await api('ai/config', { clear_key: true });
    ElMessage.success(result.key_set ? '已清除，当前使用环境变量密钥' : '已清除密钥');
    await Promise.all([loadAi(), refresh()]);
  } catch (error) {
    ElMessage.error(error.message || '清除密钥失败');
  } finally {
    aiSaving.value = false;
  }
}

onMounted(loadAi);

const roleName = computed(() => ROLE_NAMES[user.value.role] || user.value.role || '—');
const deptName = computed(
  () => users.value.find(item => item.id === user.value.id)?.dept_name || '—'
);
</script>
