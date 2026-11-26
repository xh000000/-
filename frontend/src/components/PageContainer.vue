/**
 * 页面容器（Container 布局容器）：页面骨架分两层容器——
 * 上面一个顶部框放菜单名，下面一个内容框放面板 / 表格。
 * 两个框同底色、同边框、同圆角，视觉上是一组；操作按钮属于内容，放在内容框里。
 */
<template>
  <el-container class="page-container" direction="vertical">
    <el-header class="page-container__head" height="auto">
      <div class="page-container__box">
        <div class="page-container__title">
          <h2>{{ title }}</h2>
          <p v-if="description" class="caption">{{ description }}</p>
        </div>
        <div v-if="$slots.actions" class="page-container__actions">
          <slot name="actions" />
        </div>
      </div>
    </el-header>
    <el-main class="page-container__main">
      <slot />
    </el-main>
  </el-container>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
});
</script>

<style scoped>
.page-container {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.page-container :deep(.el-header) { padding: 0; height: auto; flex: none; }
/* 内容区自己滚：标题框始终留在顶部，不随表格一起滚走 */
.page-container :deep(.el-main) { padding: 0; flex: 1; min-height: 0; overflow: auto; }

/* 顶部框：与 .panel 同一套底色/描边/圆角/阴影，读起来是两块容器而不是一行裸文字 */
.page-container__head { margin-bottom: 16px; }
.page-container__box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 13px 18px;
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--el-border-radius-base);
  box-shadow: var(--app-shadow);
}
.page-container__title h2 { font-size: 16px; line-height: 1.5; color: #183153; }
.page-container__title .caption { margin-top: 3px; max-width: 780px; }
.page-container__actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
</style>
