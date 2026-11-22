<script setup>
import { api } from "../services/api";

defineProps({
  scene: { type: Object, required: true },
  job: { type: Object, default: null },
  busy: { type: Boolean, default: false },
});
const emit = defineEmits(["edit", "delete", "generate"]);
</script>

<template>
  <div class="card">
    <div class="visual">
      <img v-if="scene.reference_asset_id" class="ref" :src="api.assetFileUrl(scene.reference_asset_id)" :alt="scene.name" />
      <div v-else class="image-placeholder">场景概念图</div>
      <div v-if="job" class="generation-overlay">
        <div class="progress-number">{{ job.status === 'pending' ? '排队中' : `${job.progress}%` }}</div>
        <div class="mini-track"><div :style="{ width: `${job.progress}%` }"></div></div>
        <span>{{ job.progress_message || '等待生成资源' }}</span>
      </div>
    </div>
    <h3>{{ scene.name }} <span class="badge" :class="scene.status">{{ scene.status }}</span></h3>
    <p class="muted">
      {{ scene.location_type === "indoor" ? "室内" : scene.location_type === "outdoor" ? "室外" : "未分类" }}
      <template v-if="scene.atmosphere"> · {{ scene.atmosphere }}</template>
    </p>
    <p class="muted description">{{ scene.environment || "（暂无环境描述）" }}</p>
    <div class="actions">
      <button :disabled="busy || !!job" @click="emit('generate', scene)">
        {{ job ? '生成中' : scene.reference_asset_id ? '重新生成' : '生成场景图' }}
      </button>
      <button class="ghost" @click="emit('edit', scene)">编辑</button>
      <button class="danger" @click="emit('delete', scene)">删除</button>
    </div>
  </div>
</template>

<style scoped>
.visual { position: relative; height: 180px; border-radius: 8px; overflow: hidden; background: #292f3d; }
.visual .ref { height: 100%; }
.image-placeholder { height: 100%; display: grid; place-items: center; color: #71717a; font-size: 13px; border: 1px dashed #41495b; border-radius: 8px; }
.generation-overlay { position: absolute; inset: 0; background: rgba(16, 19, 27, .92); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; padding: 20px; text-align: center; }
.progress-number { font-size: 25px; font-weight: 600; color: #c4b5fd; }
.generation-overlay span { font-size: 12px; color: #d4d4d8; }
.mini-track { height: 5px; width: 100%; background: #41495b; border-radius: 999px; overflow: hidden; }
.mini-track div { height: 100%; background: #818cf8; transition: width 240ms ease-out; }
.description { font-size: 13px; min-height: 40px; }
</style>
