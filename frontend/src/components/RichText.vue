<template>
  <div
    ref="host"
    class="rich-area"
    :contenteditable="editable"
    @input="onInput"
    @paste="onPaste"
  ></div>
</template>

<script setup>
import { onMounted, ref } from 'vue';

/* 只把初始 HTML 写入一次。若把 innerHTML 绑成响应式，每次输入都会重写节点，光标会跳到开头。 */
const props = defineProps({
  html: { type: String, default: '' },
  editable: { type: Boolean, default: false },
});
const emit = defineEmits(['input']);
const host = ref(null);

onMounted(() => {
  if (host.value) host.value.innerHTML = props.html || '';
});

function onInput() {
  emit('input', host.value?.innerHTML || '');
}

/* 只接收纯文本，避免把外部样式一并粘进报告。 */
function onPaste(event) {
  event.preventDefault();
  const text = event.clipboardData?.getData('text/plain') || '';
  document.execCommand('insertText', false, text);
}
</script>
