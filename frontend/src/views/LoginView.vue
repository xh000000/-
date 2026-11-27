<template>
  <div class="login-page">
    <div class="login-card">
      <div class="brand">
        <span class="mark">
          <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path d="M3 14.4 8 9.2l3 2.4 5.9-6.5" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" />
            <circle cx="16.9" cy="5.1" r="1.8" fill="#fff" />
            <path d="M3 16.9h14" stroke="#fff" stroke-opacity=".5" stroke-width="1.5" stroke-linecap="round" />
          </svg>
        </span>
        <span class="brand-text">
          <b>研枢</b>
          <small>投研平台</small>
        </span>
      </div>

      <h1>{{ setup ? '初始化管理员' : '欢迎回来' }}</h1>
      <p class="sub">期货研究管理平台 · 前后端分离部署版</p>

      <el-alert v-if="session.error" :title="session.error" type="error" show-icon :closable="false" style="margin-bottom: 16px" />

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="submit">
        <el-form-item label="账号" prop="name">
          <el-input v-model="form.name" size="large" autocomplete="username" placeholder="请输入账号" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            size="large"
            type="password"
            show-password
            :autocomplete="setup ? 'new-password' : 'current-password'"
            :placeholder="setup ? '至少 6 位' : '请输入密码'"
          />
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="form.remember">保持登录状态（30 天内免登录）</el-checkbox>
        </el-form-item>
        <el-button class="submit" type="primary" size="large" :loading="loading" native-type="submit">
          {{ setup ? '创建管理员并进入' : '登录工作空间' }}
        </el-button>
      </el-form>

      <p class="foot">
        {{ setup
          ? '初始化后请创建研究复核、合规审核、发布专员账号。'
          : '账号由管理员分配，30 分钟无操作自动退出。' }}
      </p>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { login, session } from '../store/session';

const router = useRouter();
const formRef = ref(null);
const loading = ref(false);
const setup = computed(() => session.setup);
const form = reactive({ name: '', password: '', remember: true });

const rules = computed(() => ({
  name: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: setup.value
    ? [{ required: true, min: 6, message: '初始密码至少 6 位', trigger: 'blur' }]
    : [{ required: true, message: '请输入密码', trigger: 'blur' }],
}));

async function submit() {
  try {
    await formRef.value.validate();
  } catch {
    return;
  }
  loading.value = true;
  try {
    await login(form.name.trim(), form.password, form.remember);
    ElMessage.success(setup.value ? '管理员已创建' : '登录成功');
    router.replace('/');
  } catch (error) {
    ElMessage.error(error.message || '登录失败');
  } finally {
    loading.value = false;
  }
}
</script>
