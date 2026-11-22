<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { api } from "../services/api";

const props = defineProps({ projectId: { type: String, required: true } });
const emit = defineEmits(["active-change"]);
const jobs = ref([]);
const error = ref("");
const tab = ref("active");
const busyId = ref("");
let timer = null;

const STATUS = {
  pending: "排队中",
  running: "生成中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};
const TYPE = { shot: "分镜", character: "角色", scene: "场景" };
const activeJobs = computed(() => jobs.value.filter((j) => ["pending", "running"].includes(j.status)));
const historyJobs = computed(() => jobs.value.filter((j) => !["pending", "running"].includes(j.status)));
const visibleJobs = computed(() => tab.value === "active" ? activeJobs.value : jobs.value);

async function load() {
  try {
    jobs.value = await api.listJobs(props.projectId);
    emit("active-change", activeJobs.value.length);
    error.value = "";
  } catch (e) {
    error.value = e.message;
  }
}

async function cancel(job) {
  busyId.value = job.id;
  try {
    await api.cancelJob(job.id);
    await load();
  } catch (e) {
    error.value = e.message;
  } finally {
    busyId.value = "";
  }
}

async function retry(job) {
  busyId.value = job.id;
  try {
    await api.retryJob(job.id);
    tab.value = "active";
    await load();
  } catch (e) {
    error.value = e.message;
  } finally {
    busyId.value = "";
  }
}

function fmtTime(value) {
  if (!value) return "";
  return new Date(value).toLocaleString("zh-CN", {
    month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

onMounted(() => {
  load();
  timer = setInterval(load, 2000);
});
onBeforeUnmount(() => clearInterval(timer));
</script>

<template>
  <div class="queue-page">
    <div class="queue-heading">
      <div>
        <h2>生成队列</h2>
        <p class="muted">所有分镜、角色与场景任务都在这里。离开页面也会继续生成。</p>
      </div>
      <div v-if="activeJobs.length" class="live-summary">
        <span class="live-dot"></span>{{ activeJobs.length }} 个任务进行中
      </div>
    </div>

    <div class="queue-tabs" role="tablist" aria-label="任务筛选">
      <button :class="{ selected: tab === 'active' }" @click="tab = 'active'">
        进行中 <span>{{ activeJobs.length }}</span>
      </button>
      <button :class="{ selected: tab === 'all' }" @click="tab = 'all'">
        全部记录 <span>{{ jobs.length }}</span>
      </button>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <section v-if="visibleJobs.length" class="job-list" aria-live="polite">
      <article v-for="job in visibleJobs" :key="job.id" class="job-card">
        <div class="job-main">
          <div class="job-title-row">
            <span class="job-type">{{ TYPE[job.target_type] || "分镜" }}</span>
            <h3>{{ job.target_name || "图片生成" }}</h3>
            <span class="job-status" :class="job.status">{{ STATUS[job.status] }}</span>
            <span v-if="job.status === 'pending' && job.queue_position" class="muted queue-number">
              第 {{ job.queue_position }} 位
            </span>
          </div>

          <template v-if="['pending', 'running'].includes(job.status)">
            <div class="progress-meta">
              <span>{{ job.progress_message || "等待可用生成资源" }}</span>
              <strong>{{ job.progress }}%</strong>
            </div>
            <div class="progress-track" role="progressbar" :aria-valuenow="job.progress" aria-valuemin="0" aria-valuemax="100">
              <div class="progress-fill" :class="{ waiting: job.status === 'pending' }" :style="{ width: `${job.progress}%` }"></div>
            </div>
            <p class="muted job-detail">
              {{ job.current_variation ? `当前第 ${job.current_variation}/${job.variations} 张` : `${job.variations} 张候选图` }}
              · {{ job.width }}×{{ job.height }} · {{ job.steps }} 步
            </p>
          </template>

          <div v-else class="finished-row">
            <img v-if="job.result_asset_id" :src="api.assetFileUrl(job.result_asset_id)" :alt="job.target_name" class="result-thumb" />
            <div>
              <p v-if="job.status === 'failed'" class="error job-error">{{ job.error_message }}</p>
              <p v-else class="muted job-detail">{{ fmtTime(job.completed_at || job.created_at) }} · {{ job.variations }} 张</p>
            </div>
          </div>
        </div>

        <div class="job-actions">
          <button v-if="job.status === 'pending'" class="ghost" :disabled="busyId === job.id" @click="cancel(job)">取消</button>
          <button v-if="['failed', 'cancelled'].includes(job.status)" class="ghost" :disabled="busyId === job.id" @click="retry(job)">重新排队</button>
        </div>
      </article>
    </section>

    <section v-else class="empty-queue">
      <div class="empty-icon" aria-hidden="true">✓</div>
      <h3>{{ tab === 'active' ? '当前没有排队或生成中的图片' : '还没有生成记录' }}</h3>
      <p class="muted">可从分镜画廊、角色或场景页面发起生成。</p>
    </section>
  </div>
</template>

<style scoped>
.queue-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.live-summary { color: #c4b5fd; background: #292442; border: 1px solid #443a6d; border-radius: 999px; padding: 8px 12px; font-size: 13px; white-space: nowrap; }
.live-dot { display: inline-block; width: 7px; height: 7px; background: #a78bfa; border-radius: 50%; margin-right: 7px; }
.queue-tabs { display: flex; gap: 4px; border-bottom: 1px solid #30384a; margin: 24px 0 16px; }
.queue-tabs button { background: transparent; color: #a1a1aa; border-radius: 8px 8px 0 0; border-bottom: 2px solid transparent; padding: 10px 16px; }
.queue-tabs button.selected { color: #f4f4f5; border-bottom-color: #818cf8; background: #1c2230; }
.queue-tabs button span { margin-left: 6px; color: #a5b4fc; }
.job-list { display: flex; flex-direction: column; gap: 12px; }
.job-card { display: flex; gap: 16px; align-items: center; padding: 18px 20px; border: 1px solid #2d3547; background: #1c2230; border-radius: 12px; }
.job-main { flex: 1; min-width: 0; }
.job-title-row { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
.job-title-row h3 { margin: 0; font-size: 16px; }
.job-type { color: #c4b5fd; background: #302a49; padding: 3px 8px; border-radius: 5px; font-size: 12px; }
.job-status { font-size: 12px; color: #a1a1aa; }
.job-status.running { color: #fcd34d; }
.job-status.completed { color: #86efac; }
.job-status.failed { color: #fca5a5; }
.queue-number { font-size: 12px; }
.progress-meta { display: flex; justify-content: space-between; gap: 16px; margin: 16px 0 8px; font-size: 13px; color: #d4d4d8; }
.progress-meta strong { color: #c4b5fd; font-size: 15px; }
.progress-track { height: 7px; background: #30384a; border-radius: 999px; overflow: hidden; }
.progress-fill { height: 100%; background: #818cf8; border-radius: inherit; transition: width 240ms ease-out; }
.progress-fill.waiting { background: #52525b; }
.job-detail { font-size: 12px; margin: 8px 0 0; }
.job-actions { flex-shrink: 0; }
.finished-row { display: flex; align-items: center; gap: 12px; margin-top: 10px; }
.result-thumb { width: 64px; height: 48px; object-fit: cover; border-radius: 6px; }
.job-error { font-size: 13px; margin: 6px 0 0; max-width: 680px; }
.empty-queue { text-align: center; padding: 72px 20px; border: 1px dashed #384155; border-radius: 14px; margin-top: 20px; }
.empty-icon { color: #86efac; font-size: 24px; margin-bottom: 8px; }
.empty-queue h3 { margin: 8px 0; }
@media (max-width: 700px) { .queue-heading, .job-card { align-items: stretch; flex-direction: column; } .live-summary { align-self: flex-start; } .job-actions { align-self: flex-end; } }
</style>
