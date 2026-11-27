<template>
  <div class="agent-page">
    <PageContainer title="AI 问答">
      <template #actions>
        <span v-if="status?.configured" class="tiny agent-model">模型：{{ status.model }}</span>
        <el-button v-if="canGenerate" @click="jobsVisible = true">生成记录<span v-if="activeJobCount"> · {{ activeJobCount }} 进行中</span></el-button>
        <el-button :loading="threadsLoading" @click="loadThreads">刷新</el-button>
      </template>

    <el-drawer v-if="canGenerate" v-model="jobsVisible" title="研报生成记录" size="min(560px, 100vw)">
    <section class="report-workbench">
      <div class="report-workbench-head">
        <div><b>最近生成任务</b></div>
        <el-button :loading="jobsLoading" @click="loadReportJobs">刷新任务</el-button>
      </div>
      <p v-if="jobsError" role="alert">{{ jobsError }}</p>
      <p v-else-if="!reportJobs.length" class="caption">还没有生成任务。点击「AI 生成研报」开始；已有草稿也可在编辑器中继续生成。</p>
      <div v-for="job in reportJobs" :key="job.id" class="report-job">
        <div><b>{{ job.title }}</b><span v-if="job.shared" class="caption"> · 协作任务 / {{ job.initiator }}</span><p class="caption">{{ (job.created_at || '').replace(/\.\d+(?= UTC$)/, '') }} · {{ job.result.stage || job.status }} · {{ job.result.completed || 0 }}/{{ job.result.total || 0 }} 章</p><p v-if="job.error" class="report-job-error">{{ job.error }}</p></div>
        <el-tag>{{ ['已完成','部分采用'].includes(job.status) ? '候选待确认' : job.status }}</el-tag>
        <el-button @click="openReportJob(job)">{{ ['已完成','部分采用'].includes(job.status) ? '查看候选' : '打开研报' }}</el-button>
      </div>
    </section>
    </el-drawer>
    <NewReportDialog v-model="reportDialog" ai-mode @created="createdReport" />

    <el-alert
      v-if="status && !status.configured"
      type="warning"
      show-icon
      :closable="false"
      class="agent-alert"
    >
      <template #title>Agent 模型未配置</template>
      管理员请在项目根目录 .env 设置 AGENT_API_KEY 与 AGENT_MODEL（未设置的项会回落到「系统设置 → 外部模型」的平台配置），重启后端后即可使用。
    </el-alert>

    <div v-if="status" class="agent-body">
      <div class="panel agent-threads">
        <div class="agent-threads-head">
          <b>对话线程</b>
          <el-button size="small" type="primary" plain @click="newThread">＋ 新对话</el-button>
        </div>
        <div class="agent-threads-scroll">
          <div
            v-for="t in threads"
            :key="t.id"
            class="agent-thread"
            :class="{ on: t.id === threadId }"
            role="button"
            tabindex="0"
            @click="openThread(t)"
            @keydown.enter="openThread(t)"
          >
            <div class="agent-thread-row">
              <span class="ellipsis agent-thread-title" :title="t.title || '新对话'">{{ t.title || '新对话' }}</span>
              <span class="agent-thread-del tiny" title="删除线程（连同记忆）" @click.stop="removeThread(t)">删除</span>
            </div>
            <span class="tiny">{{ shortTime(t.updated_at) }}</span>
          </div>
          <p v-if="!threads.length && !threadsLoading" class="caption agent-threads-empty">
            还没有对话，点上方「＋ 新对话」开始
          </p>
        </div>
        <div v-if="canGenerate" class="agent-report-entry">
          <span class="agent-entry-label">从研究到成稿</span>
          <p>沿用分类模板和 Skill，生成有数据依据的研报候选。</p>
          <el-button class="agent-report-button" @click="reportDialog = true"><el-icon><DocumentAdd /></el-icon><span>AI 生成研报</span></el-button>
          <button class="agent-report-link" type="button" @click="router.push('/reports')">前往研报中心</button>
        </div>
      </div>

      <div class="panel agent-chat">
        <div class="agent-messages" ref="scroller">
          <div v-if="!messages.length" class="agent-welcome">
            <h3>{{ greeting }}，{{ userName }}</h3>
            <p class="caption">我可以帮你查研报与指标数据、检索资料库，并把整理好的内容写成章节草稿。试试：</p>
            <div class="agent-suggest">
              <button v-for="s in suggestions" :key="s" type="button" @click="quick(s)">{{ s }}</button>
            </div>
          </div>

          <template v-for="(m, i) in messages" :key="i">
            <div v-if="m.role === 'user'" class="agent-msg agent-msg-user">
              <div class="agent-bubble">{{ m.content }}</div>
            </div>
            <div v-else class="agent-msg agent-msg-ai">
              <div v-if="m.tools?.length" class="agent-tools">
                <span v-for="(t, j) in m.tools" :key="j" class="agent-tool" :title="t.output || '执行中…'">
                  {{ toolLabel(t.name) }}
                  <b v-if="t.output">✓</b>
                  <span v-else class="agent-tool-running">…</span>
                </span>
              </div>
              <div v-if="m.content" class="agent-bubble" v-html="render(m.content)"></div>
              <div v-if="m.streaming && !m.content" class="agent-typing">
                <span></span><span></span><span></span>
              </div>
              <div v-if="m.error" class="agent-bubble agent-bubble-error">{{ m.error }}</div>
            </div>
          </template>
        </div>

        <div class="agent-input">
          <el-input
            v-model="input"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            placeholder="输入问题，Ctrl+Enter 发送…"
            :disabled="streaming"
            @keydown="onKey"
          />
          <div class="agent-input-bar">
            <span class="tiny">内容由 AI 生成，数据以平台录入为准；写入章节均为候选草稿，须人工核对</span>
            <span class="grow"></span>
            <el-button v-if="streaming" @click="stop">停止</el-button>
            <el-button v-else type="primary" :disabled="!input.trim()" @click="send">发送</el-button>
          </div>
        </div>
      </div>
    </div>
    </PageContainer>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { createdReportRoute } from '../utils/reportCreation';
import { DocumentAdd } from '@element-plus/icons-vue';
import NewReportDialog from '../components/NewReportDialog.vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import PageContainer from '../components/PageContainer.vue';
import { api, del } from '../api';
import { user } from '../store/session';

const TOOL_LABELS = {
  list_reports: '检索研报',
  get_report: '读取研报',
  search_indicators: '检索指标',
  query_indicator: '查询指标数据',
  list_commodities: '查询品种库',
  search_library: '检索资料库',
  save_chapter_draft: '保存章节候选',
};

const suggestions = [
  '查一下平台里有哪些期货品种板块',
  '帮我看看最近的研报列表',
  '查一下铜库存最近的走势，做个小结',
  '把今天宏观要闻的框架草稿写出来',
];

const status = ref(null);
const threads = ref([]);
const threadsLoading = ref(false);
const threadId = ref('');
const messages = ref([]);
const input = ref('');
const streaming = ref(false);
const router = useRouter();
const reportDialog = ref(false);
const jobsVisible = ref(false);
const activeJobCount = computed(() => reportJobs.value.filter(j => ['排队中','运行中'].includes(j.status)).length);
const canGenerate = computed(() => ['admin', 'researcher'].includes(user.value.role));
const reportJobs = ref([]);
const jobsLoading = ref(false);
const jobsError = ref('');
let jobsTimer;
let disposed = false;
const createdReport = (id, options) => router.push(createdReportRoute(id, options));
const openReportJob = job => router.push({name:'editor',params:{id:job.report_id},query:job.editable ? {ai:'1'} : {}});
async function loadReportJobs() {
  if (!canGenerate.value || jobsLoading.value || disposed) return;
  jobsLoading.value = true;
  try {
    const result = await api('report-ai/recent-jobs');
    if (!disposed) { reportJobs.value = result.jobs || []; jobsError.value = ''; }
  } catch (error) {
    if (!disposed) jobsError.value = error.message || '生成任务加载失败';
  } finally {
    jobsLoading.value = false;
    clearTimeout(jobsTimer);
    if (!disposed && reportJobs.value.some(j => ['排队中','运行中'].includes(j.status))) jobsTimer = setTimeout(loadReportJobs, 5000);
  }
}
const scroller = ref(null);
let controller = null;

const userName = computed(() => user.value.name || '同事');
const greeting = computed(() => {
  const hour = new Date().getHours();
  if (hour < 6) return '夜深了';
  if (hour < 12) return '早上好';
  if (hour < 18) return '下午好';
  return '晚上好';
});

function toolLabel(name) {
  return TOOL_LABELS[name] || name;
}

function shortTime(value) {
  if (!value) return '';
  // 线程时间是 UTC 文本（YYYY-MM-DD HH:MM:SS UTC），展示成年月日即可
  return (value || '').slice(0, 10);
}

/* 极简 Markdown：标题加粗、**加粗**、- 列表；先转义再替换，不引入渲染库。 */
function render(text) {
  const esc = String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return esc.replace(/^#{2,4}\s*(.+)$/gm, '<b>$1</b>')
    .replace(/^[-*]\s+(.+)$/gm, '· $1')
    .replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>');
}

function scrollBottom() {
  nextTick(() => {
    const el = scroller.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}

async function loadStatus() {
  try {
    status.value = await api('agent/status');
  } catch (error) {
    ElMessage.error(error.message || '读取 Agent 状态失败');
    status.value = { configured: false };
  }
}

async function loadThreads() {
  threadsLoading.value = true;
  try {
    threads.value = (await api('agent/threads')).threads || [];
  } catch (error) {
    ElMessage.error(error.message || '读取对话线程失败');
  } finally {
    threadsLoading.value = false;
  }
}

async function openThread(t) {
  if (streaming.value) return;
  threadId.value = t.id;
  messages.value = [];
  try {
    const result = await api(`agent/threads/${t.id}/messages`);
    messages.value = (result.messages || []).map(m => ({ role: m.role, content: m.content }));
    scrollBottom();
  } catch (error) {
    ElMessage.error(error.message || '读取历史消息失败');
  }
}

async function newThread() {
  if (streaming.value) return;
  threadId.value = '';
  messages.value = [];
}

async function removeThread(t) {
  try {
    await ElMessageBox.confirm(`删除对话「${t.title || '新对话'}」？记忆一并清除，不可恢复。`, '删除线程', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    });
  } catch {
    return;
  }
  try {
    await del(`agent/threads/${t.id}`);
    if (threadId.value === t.id) { threadId.value = ''; messages.value = []; }
    await loadThreads();
  } catch (error) {
    ElMessage.error(error.message || '删除失败');
  }
}

function quick(text) {
  if (streaming.value) return;
  input.value = text;
  send();
}

function onKey(event) {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault();
    send();
  }
}

async function ensureThread(title) {
  if (threadId.value) return threadId.value;
  const created = await api('agent/threads', { title: title.slice(0, 60) });
  threadId.value = created.id;
  await loadThreads();
  return created.id;
}

async function send() {
  const text = input.value.trim();
  if (!text || streaming.value || !status.value?.configured) return;
  const reply = reactive({ role: 'assistant', content: '', tools: [], error: '', streaming: true });
  messages.value.push({ role: 'user', content: text });
  input.value = '';
  messages.value.push(reply);
  streaming.value = true;
  controller = new AbortController();
  scrollBottom();
  try {
    const tid = await ensureThread(text);
    const res = await fetch('/api/agent/chat', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ thread_id: tid, message: text }),
      signal: controller.signal,
    });
    if (!res.ok || !res.body) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || `请求失败（${res.status}）`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let ended = false;
    while (!ended) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf('\n\n')) >= 0) {
        const chunk = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data: ')) continue;
          let event;
          try {
            event = JSON.parse(line.slice(6));
          } catch {
            continue;
          }
          if (event.type === 'start') threadId.value = event.thread_id;
          else if (event.type === 'token') { reply.content += event.content; scrollBottom(); }
          else if (event.type === 'tool_start') reply.tools.push({ name: event.name, args: event.args, output: '' });
          else if (event.type === 'tool_end') {
            const tool = [...reply.tools].reverse().find(item => item.name === event.name && !item.output);
            if (tool) tool.output = event.output;
          } else if (event.type === 'error') reply.error = event.message;
          else if (event.type === 'done') ended = true;
        }
      }
    }
    reply.streaming = false;
    loadThreads(); // 标题与活跃时间可能已更新
  } catch (error) {
    reply.streaming = false;
    if (error.name === 'AbortError') {
      reply.error = reply.content ? '' : '已停止本次回答';
    } else {
      reply.error = error.message || '请求失败';
      ElMessage.error(reply.error);
    }
  } finally {
    streaming.value = false;
    controller = null;
    scrollBottom();
  }
}

function stop() {
  if (controller) controller.abort();
}

onMounted(() => {
  loadReportJobs();
  loadStatus();
  loadThreads();
});
onUnmounted(() => { disposed = true; clearTimeout(jobsTimer); stop(); });
</script>

<style scoped>
.agent-model { padding:6px 10px; border-radius:20px; background:var(--el-fill-color-light); }
.agent-report-entry { padding:18px 14px; border-top:1px solid var(--el-border-color-lighter); background:var(--el-fill-color-extra-light); }
.agent-entry-label { font-size:12px; font-weight:600; color:var(--el-text-color-secondary); }
.agent-report-entry p { font-size:12px; line-height:1.7; color:var(--el-text-color-secondary); margin:8px 0 14px; }
.agent-report-button { width:100%; justify-content:flex-start; height:40px; border-color:var(--el-color-primary-light-7); color:var(--el-color-primary); }
.agent-report-button :deep(>span) { display:flex; align-items:center; width:100%; gap:8px; }
.agent-report-button :deep(>span>span:last-child) { margin-left:auto; }
.agent-report-link { margin-top:12px; padding:0; background:none; border:0; color:var(--el-text-color-secondary); font:inherit; font-size:12px; cursor:pointer; }
.agent-report-link:hover { color:var(--el-color-primary); }
.report-workbench-head,.report-job { display:flex; align-items:center; gap:12px; }
.report-workbench-head>div,.report-job>div { flex:1; min-width:0; }
.report-workbench p { margin:8px 0; line-height:1.6; }
.report-job { padding:18px 0; border-bottom:1px solid var(--el-border-color-lighter); flex-wrap:wrap; }
.report-job>div { flex-basis:100%; }
.report-job-error { color:var(--el-color-danger); overflow-wrap:anywhere; }
.agent-welcome h3 { font-size:22px; font-weight:600; letter-spacing:-.02em; color:var(--ink-1); }
.agent-welcome { max-width:560px; }
.agent-suggest { margin-top:24px; }
@media(max-width:760px) { .agent-threads { max-height:300px; } .agent-report-entry { padding:12px; } .agent-report-entry p { display:none; } .agent-report-button { margin-top:8px; } }
</style>
