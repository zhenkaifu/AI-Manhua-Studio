<script setup>
import { onMounted, ref } from 'vue';
import { api } from '../services/api';
import AssetsView from './AssetsView.vue';
const props = defineProps({ projects: Array, initialProjectId: String });
const selected = ref(''); const loading = ref(true);
onMounted(() => { selected.value = props.initialProjectId || props.projects[0]?.id || ''; loading.value = false; });
</script>
<template>
  <div class="page-container asset-library">
    <header class="library-heading"><div><p class="overline">ASSET LIBRARY</p><h1>视觉资产库</h1><p>集中查看项目中的角色参考图、场景参考图与分镜定稿素材。</p></div><select v-if="projects.length" v-model="selected" aria-label="选择项目"><option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option></select></header>
    <div v-if="selected" class="library-body"><AssetsView :key="selected" :project-id="selected" /></div>
    <div v-else-if="!loading" class="library-empty">还没有项目。请先创建一个漫剧项目。</div>
  </div>
</template>
<style scoped>
.library-heading{display:flex;justify-content:space-between;align-items:center;gap:20px;margin:18px 0 26px}.overline{font-size:10px;letter-spacing:1.6px;color:var(--accent);font-weight:700;margin:0}.library-heading h1{font-size:30px;margin:6px 0 8px}.library-heading p:not(.overline){color:var(--text-secondary);margin:0;font-size:13px}.library-heading select{min-width:220px}.library-body{background:var(--surface);border:1px solid var(--border);border-radius:13px;padding:22px}.library-body :deep(h2){display:none}.library-body :deep(.grid){margin-top:0}.library-body :deep(.card){background:var(--surface);border:1px solid var(--border);padding:12px}.library-body :deep(.card img.ref){background:#eef1f4}.library-empty{padding:100px;text-align:center;border:1px dashed var(--border-strong);border-radius:12px;color:var(--text-secondary)}@media(max-width:600px){.library-heading{align-items:flex-start;flex-direction:column}.library-heading select{width:100%}.library-heading h1{font-size:26px}}
</style>
