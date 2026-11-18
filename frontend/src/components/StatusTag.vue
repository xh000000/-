<template>
  <el-tag :type="type" size="small" effect="light" disable-transitions>{{ text }}</el-tag>
</template>

<script setup>
import { computed } from 'vue';
import { TAG_TYPE, statusText } from '../utils/format';

const props = defineProps({ report: { type: Object, required: true } });

const text = computed(() => statusText(props.report));
const type = computed(() => TAG_TYPE[props.report.status] || 'info');
</script>
