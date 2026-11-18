<template>
  <el-dialog v-model="visible" title="修改密码" width="420px" :close-on-click-modal="false" @closed="reset">
    <el-form ref="formRef" :model="form" :rules="rules" label-width="92px" @submit.prevent="submit">
      <el-form-item label="原密码" prop="old">
        <el-input v-model="form.old" type="password" show-password autocomplete="current-password" />
      </el-form-item>
      <el-form-item label="新密码" prop="next">
        <el-input v-model="form.next" type="password" show-password autocomplete="new-password" />
      </el-form-item>
      <el-form-item label="确认新密码" prop="confirm">
        <el-input v-model="form.confirm" type="password" show-password autocomplete="new-password" />
      </el-form-item>
      <p class="caption">修改后当前账号的全部登录会话立即失效，需要使用新密码重新登录。</p>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { api } from '../api';
import { session } from '../store/session';

const visible = defineModel({ type: Boolean, default: false });
const router = useRouter();
const formRef = ref(null);
const saving = ref(false);
const form = reactive({ old: '', next: '', confirm: '' });

const rules = {
  old: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  next: [{ required: true, min: 6, message: '新密码至少 6 位', trigger: 'blur' }],
  confirm: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (value !== form.next) callback(new Error('两次输入的新密码不一致'));
        else callback();
      },
      trigger: 'blur',
    },
  ],
};

function reset() {
  form.old = '';
  form.next = '';
  form.confirm = '';
  formRef.value?.clearValidate();
}

async function submit() {
  try {
    await formRef.value.validate();
  } catch {
    return;
  }
  saving.value = true;
  try {
    await api('password', { old: form.old, new: form.next });
    visible.value = false;
    ElMessage.success('密码已修改，请重新登录');
    session.data = null;
    setTimeout(() => router.replace({ name: 'login' }), 600);
  } catch (error) {
    ElMessage.error(error.message || '修改失败');
  } finally {
    saving.value = false;
  }
}
</script>
