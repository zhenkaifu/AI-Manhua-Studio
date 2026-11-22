<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { api } from "../services/api";
import CharacterCard from "../components/CharacterCard.vue";
import CharacterEditor from "../components/CharacterEditor.vue";

const props = defineProps({ projectId: { type: String, required: true } });
const characters = ref([]);
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
    [characters.value, jobs.value] = await Promise.all([
      api.listCharacters(props.projectId),
      api.listJobs(props.projectId),
    ]);
    jobs.value = jobs.value.filter((j) => j.target_type === "character");
  } catch (e) {
    error.value = e.message;
  }
}

function openCreate() { editing.value = null; showEditor.value = true; }
function openEdit(c) { editing.value = c; showEditor.value = true; }

async function generate(c) {
  busyId.value = c.id;
  error.value = "";
  try {
    await api.generateCharacter(c.id);
    notice.value = `「${c.name}」已加入生成队列，完成后会自动更新参考图。`;
    await load();
  } catch (e) {
    error.value = e.message;
  } finally {
    busyId.value = "";
  }
}

async function remove(c) {
  if (!window.confirm(`确定删除角色「${c.name}」吗？（参考图片会保留在资产库）`)) return;
  await api.deleteCharacter(c.id);
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
      <h2>角色管理</h2>
      <p class="muted">角色设定会被 AI 提取和图片生成复用，也可以直接生成角色设定图。</p>
    </div>
    <span v-if="activeJobs.length" class="badge">{{ activeJobs.length }} 个角色生成中</span>
  </div>

  <button @click="openCreate">+ 新建角色</button>
  <p v-if="notice" class="success">{{ notice }}</p>
  <p v-if="error" class="error">{{ error }}</p>
  <p v-if="!characters.length" class="muted" style="margin-top: 16px">
    还没有角色。可以手动新建，或到「AI 提取」页从小说中自动识别。
  </p>

  <div class="grid">
    <CharacterCard
      v-for="c in characters"
      :key="c.id"
      :character="c"
      :job="jobFor(c.id)"
      :busy="busyId === c.id"
      @generate="generate"
      @edit="openEdit"
      @delete="remove"
    />
  </div>

  <CharacterEditor v-if="showEditor" :project-id="projectId" :character="editing" @saved="onSaved" @close="showEditor = false" />
</template>

<style scoped>
.view-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.success { color: #86efac; }
</style>
