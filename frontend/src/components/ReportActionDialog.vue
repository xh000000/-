<template>
  <div>
    <el-dialog v-model="visible" title="研报操作" width="520px">
      <template v-if="report">
        <h3 style="margin-bottom: 4px">{{ report.title }}</h3>
        <p class="caption" style="margin-bottom: 14px">
          <StatusTag :report="report" />
          <span style="margin-left: 8px">v{{ report.version }} · 第{{ report.issue || 1 }}期 · {{ report.author_name }}</span>
        </p>

        <div class="row" style="flex-wrap: wrap; gap: 8px">
          <el-button @click="act('open')">{{ editable ? '编辑' : '查看' }}</el-button>
          <el-button v-if="can('提交')" type="primary" plain @click="act('submit')">提交审批</el-button>
          <el-button v-if="can('通过')" type="primary" @click="act('approve')">审核通过</el-button>
          <el-button v-if="can('退回')" type="warning" plain @click="act('reject')">驳回</el-button>
          <el-button v-if="can('发布')" type="success" @click="act('publish')">发布</el-button>
          <el-button v-if="report.can_schedule" @click="act('schedule')">定时发布</el-button>
          <el-button v-if="owner && editable" type="danger" plain @click="act('delete')">删除</el-button>
          <el-button v-if="owner && !editable" @click="act('withdraw')">撤销</el-button>
          <el-button v-if="['已发布', '待发布'].includes(report.status)" @click="act('print')">下载 PDF</el-button>
        </div>

        <p class="caption" style="margin-top: 16px">
          PDF 通过服务端打印页生成（浏览器「打印 → 另存为 PDF」）。
          长图导出需要引入前端截图库，当前版本未实现。
        </p>
      </template>

      <el-empty v-else description="报告不存在或无权访问" :image-size="70" />
    </el-dialog>

    <el-dialog v-model="scheduleVisible" title="定时发布" width="420px" :close-on-click-modal="false">
      <el-form label-width="96px">
        <el-form-item label="发布时间">
          <el-date-picker
            v-model="scheduleAt"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm"
            placeholder="选择日期与时间"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <p class="caption">到达预约时间后由服务端自动发布并写入操作留痕。留空保存则取消定时。</p>
      <template #footer>
        <el-button @click="scheduleVisible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="saveSchedule">保存定时</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import StatusTag from './StatusTag.vue';
import { api, printUrl } from '../api';
import { refresh, reports, user } from '../store/session';

const props = defineProps({ reportId: { type: [Number, String], default: null } });
const emit = defineEmits(['open']);
const visible = defineModel({ type: Boolean, default: false });

const router = useRouter();
const busy = ref(false);
const scheduleVisible = ref(false);
const scheduleAt = ref('');

const report = computed(() => reports.value.find(item => item.id === Number(props.reportId)) || null);
const owner = computed(() => report.value && (report.value.author === user.value.id || user.value.role === 'admin'));
const editable = computed(
  () => report.value && report.value.author === user.value.id && ['草稿', '已退回'].includes(report.value.status)
);
const can = action => Boolean(report.value?.allowed_actions?.includes(action));

async function act(name) {
  const current = report.value;
  if (!current) return;
  if (name === 'open') {
    visible.value = false;
    emit('open', current.id);
    return;
  }
  if (name === 'print') {
    window.open(printUrl(current.id), '_blank');
    return;
  }
  if (name === 'delete') {
    try {
      await ElMessageBox.confirm('从业务列表移除该草稿，数据库记录保留。', '删除研报', {
        confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
      });
    } catch {
      return;
    }
    await send('report-delete', { id: current.id }, '已删除');
    return;
  }
  if (name === 'schedule') {
    scheduleAt.value = '';
    scheduleVisible.value = true;
    return;
  }
  if (name === 'withdraw') {
    let note = '';
    try {
      const result = await ElMessageBox.prompt('撤销后退出当前发布 / 审批状态，历史定稿与审批记录保留。', '撤销发布或审批', {
        confirmButtonText: '确认撤销', cancelButtonText: '取消',
        inputType: 'textarea', inputPlaceholder: '请填写撤销原因', inputValidator: v => Boolean(v?.trim()) || '必须填写撤销原因',
      });
      note = result.value;
    } catch {
      return;
    }
    await send('report-withdraw', { id: current.id, note }, '已撤销');
    return;
  }
  if (name === 'reject') {
    let note = '';
    try {
      const result = await ElMessageBox.prompt(`当前状态：${current.status}`, '驳回研报', {
        confirmButtonText: '确认驳回', cancelButtonText: '取消',
        inputType: 'textarea', inputPlaceholder: '请填写驳回理由', inputValidator: v => Boolean(v?.trim()) || '必须填写驳回理由',
      });
      note = result.value;
    } catch {
      return;
    }
    await send('transition', transitionPayload(current, '退回', note), '流程已更新');
    return;
  }
  if (name === 'approve' || name === 'publish') {
    const label = name === 'approve' ? '审核通过' : '发布';
    try {
      await ElMessageBox.confirm(`确认对「${current.title}」执行${label}？操作会绑定当前版本。`, label, {
        confirmButtonText: label, cancelButtonText: '取消', type: name === 'publish' ? 'success' : 'info',
      });
    } catch {
      return;
    }
    await send('transition', transitionPayload(current, name === 'approve' ? '通过' : '发布', ''), '流程已更新');
    return;
  }
  if (name === 'submit') {
    await send('transition', transitionPayload(current, '提交', ''), '已提交审批');
  }
}

function transitionPayload(current, action, note) {
  return {
    id: current.id,
    action,
    note,
    expected_status: current.status,
    expected_workflow: current.workflow_state,
  };
}

async function send(path, payload, message) {
  busy.value = true;
  try {
    await api(path, payload);
    await refresh();
    ElMessage.success(message);
    visible.value = false;
  } catch (error) {
    ElMessage.error(error.message || '操作失败');
  } finally {
    busy.value = false;
  }
}

async function saveSchedule() {
  if (!report.value) return;
  busy.value = true;
  try {
    await api('report-schedule', { id: report.value.id, at: scheduleAt.value || '' });
    await refresh();
    scheduleVisible.value = false;
    visible.value = false;
    ElMessage.success(scheduleAt.value ? '已设置定时发布' : '已取消定时发布');
  } catch (error) {
    ElMessage.error(error.message || '设置失败');
  } finally {
    busy.value = false;
  }
}
</script>
