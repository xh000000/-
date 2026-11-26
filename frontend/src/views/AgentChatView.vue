<template>
  <div class="agent-page">
    <PageHead
      title="AI 问答"
      description="内置投研 Agent：查研报、取指标、读资料库，并把候选章节草稿写回平台；生成内容须人工核对后方可送审。"
    >
      <span v-if="status?.configured" class="tiny">模型：{{ status.model }}</span>
      <el-button :loading="pipelineLoading" @click="runPipeline">AI 日报</el-button>
      <el-button :loading="threadsLoading" @click="loadThreads">刷新</el-button>
    </PageHead>

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

    <div v-else-if="status" class="agent-body">
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
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import PageHead from '../components/PageHead.vue';
import { api, del } from '../api';
import { user } from '../store/session';

const TOOL_LABELS = {
  list_reports: '检索研报',
  get_report: '读取研报',
  search_indicators: '检索指标',
  query_indicator: '查询指标数据',
  list_commodities: '查询品种库',
  search_library: '检索资料库',
  save_chapter_draft: '写入章节草稿',
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
const pipelineLoading = ref(false);
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

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

/* AI 日报流水线：确认 → 排队 → 轮询任务直到完成/失败 */
async function runPipeline() {
  try {
    await ElMessageBox.confirm(
      '流水线将自动取数、逐板块生成初稿、创建报告并推进到「研究复核」（整篇标记 AI 初稿，须人工复核后才能发布）。继续？',
      'AI 日报流水线', { confirmButtonText: '开始生成', cancelButtonText: '取消', type: 'info' },
    );
  } catch {
    return;
  }
  pipelineLoading.value = true;
  try {
    const task = await api('agent/pipeline/run', {});
    ElMessage.info('流水线任务已排队，后台生成中（通常需要几分钟）…');
    for (let i = 0; i < 120; i++) {
      await sleep(3000);
      const t = await api(`agent/tasks/${task.id}`);
      if (t.status === '已完成') {
        let summary = {};
        try { summary = JSON.parse(t.result || '{}'); } catch { /* 结果非 JSON 时忽略 */ }
        const okCount = (summary.sections || []).filter(s => s.ok).length;
        ElMessageBox.alert(
          `《${summary.title || '日度策略'}》初稿已生成${summary.submitted ? '，并已进入研究复核' : '（未能自动送审，请在报告中手动提交）'}。`
          + `成功撰写 ${okCount}/${(summary.sections || []).length} 个章节。请在研报中心查看并复核。`,
          '流水线完成', { confirmButtonText: '知道了' },
        );
        return;
      }
      if (t.status === '失败') {
        ElMessage.error(t.error || '流水线执行失败');
        return;
      }
    }
    ElMessage.warning('任务仍在后台运行，可稍后在任务列表查看结果');
  } catch (error) {
    ElMessage.error(error.message || '触发流水线失败');
  } finally {
    pipelineLoading.value = false;
  }
}

onMounted(() => {
  loadStatus();
  loadThreads();
});
</script>
