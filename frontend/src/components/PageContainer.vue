/**
 * 页面骨架（全站唯一）：一张整卡，上部是标题栏（底部分隔线），下部是内容区。
 * 标题栏只放页面名与主操作；筛选、表格等内容都在下方内容区里，随内容区滚动。
 */
<template>
  <el-container class="page-container" direction="vertical">
    <div class="page-container__card">
      <div class="page-container__head">
        <h2>{{ title }}</h2>
        <div v-if="$slots.actions" class="page-container__actions">
          <slot name="actions" />
        </div>
      </div>
      <div class="page-container__body">
        <slot />
      </div>
    </div>
  </el-container>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
});
</script>

<style scoped>
.page-container {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.page-container__card {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
}
.page-container__head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 50px;
  padding: 10px 20px;
  border-bottom: 1px solid var(--line-2);
}
.page-container__head h2 { font-size: 15px; line-height: 1.4; font-weight: 600; color: var(--ink-1); }
.page-container__actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.page-container__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 16px 20px 20px;
}
</style>
