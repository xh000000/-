<template>
  <div class="page-head">
    <div>
      <h2>{{ title }}</h2>
      <p v-if="description" class="caption">{{ description }}</p>
    </div>
    <div class="row">
      <slot />
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
});
</script>
