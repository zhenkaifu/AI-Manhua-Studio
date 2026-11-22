<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { api } from "../services/api";
import SceneCard from "../components/SceneCard.vue";
import SceneEditor from "../components/SceneEditor.vue";

const props = defineProps({ projectId: { type: String, required: true } });
const scenes = ref([]);
const jobs = ref([]);
const error = ref("");
const notice = ref("");
const editing = ref(null);
const showEditor = ref(false);
const busyId = ref("");
let pollTimer = null;

const activeJobs = computed(() => jobs.value.filter((j) => ["pending", "running"].includes(j.status)));
const jobFor = (id) => jobs.value.find((j) => j.target_id === id && ["pending", "running"].includes(j.status));

async function load() {
  try {
    [scenes.value, jobs.value] = await Promise.all([
      api.listScenes(props.projectId),
      api.listJobs(props.projectId),
    ]);
    jobs.value = jobs.value.filter((j) => j.target_type === "scene");
  } catch (e) {
    error.value = e.message;
  }
}

function openCreate() { editing.value = null; showEditor.value = true; }
function openEdit(s) { editing.value = s; showEditor.value = true; }

async function generate(s) {
  busyId.value = s.id;
  error.value = "";
  try {
    await api.generateScene(s.id);
    notice.value = `「${s.name}」已加入生成队列，完成后会自动更新参考图。`;
    await load();
  } catch (e) {
    error.value = e.message;
  } finally {
    busyId.value = "";
  }
}

async function remove(s) {
  if (!window.confirm(`确定删除场景「${s.name}」吗？`)) return;
  await api.deleteScene(s.id);
  load();
}

async function onSaved() { showEditor.value = false; await load(); }

onMounted(() => {
  load();
  pollTimer = setInterval(load, 2000);
});
onBeforeUnmount(() => clearInterval(pollTimer));
</script>

<template>
  <div class="view-heading">
    <div>
      <h2>场景管理</h2>
      <p class="muted">场景设定保证同一个地点在不同镜头中保持一致的视觉。</p>
    </div>
    <span v-if="activeJobs.length" class="badge">{{ activeJobs.length }} 个场景生成中</span>
  </div>

  <button @click="openCreate">+ 新建场景</button>
  <p v-if="notice" class="success">{{ notice }}</p>
  <p v-if="error" class="error">{{ error }}</p>
  <p v-if="!scenes.length" class="muted" style="margin-top: 16px">
    还没有场景。可以手动新建，或到「AI 提取」页从小说中自动识别。
  </p>

  <div class="grid">
    <SceneCard
      v-for="s in scenes"
      :key="s.id"
      :scene="s"
      :job="jobFor(s.id)"
      :busy="busyId === s.id"
      @generate="generate"
      @edit="openEdit"
      @delete="remove"
    />
  </div>

  <SceneEditor v-if="showEditor" :project-id="projectId" :scene="editing" @saved="onSaved" @close="showEditor = false" />
</template>

<style scoped>
.view-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.success { color: #86efac; }
</style>
