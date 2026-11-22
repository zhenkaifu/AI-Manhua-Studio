<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { api } from "../services/api";

const props = defineProps({
  projectId: { type: String, required: true },
  preferredEpisodeId: { type: String, default: "" },
});
const emit = defineEmits(["select-episode", "updated"]);

const episodes = ref([]);
const episodeId = ref("");
const gallery = ref(null);
const error = ref("");
const notice = ref("");
const busy = ref(false);
const compareImg = ref(null); // 放大查看的图片
const editShotId = ref(null); // 正在编辑 Prompt 的分镜
const promptDraft = ref({ prompt: "", negative_prompt: "", is_custom: false });
const regenParams = ref({ seed: "", steps: 6, variations: 1, size: "1024x576" });
const promptSaving = ref(false);
const promptError = ref("");
const comparePair = ref([]); // 对比模式选中的两张图
const showCompare = ref(false);
const refOptions = ref({ characters: [], scene: null }); // 编辑器里的参考图选项
const refSelected = ref([]); // 编辑器勾选的参考图 asset_id
let pollTimer = null;

const STATUS_LABEL = {
  pending: "排队中",
  running: "生成中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const hasActive = computed(
  () => gallery.value?.shots.some((s) => s.active_job) ?? false
);

async function loadEpisodes() {
  try {
    episodes.value = await api.listEpisodes(props.projectId);
    if (episodes.value.length && !episodeId.value) {
      episodeId.value = episodes.value.some(e => e.id === props.preferredEpisodeId)
        ? props.preferredEpisodeId
        : episodes.value[episodes.value.length - 1].id;
      emit("select-episode", episodeId.value);
      await loadGallery();
    }
  } catch (e) {
    error.value = e.message;
  }
}

function changeEpisode(event) {
  episodeId.value = event.target.value;
  emit("select-episode", episodeId.value);
  loadGallery();
}

watch(() => props.preferredEpisodeId, value => {
  if (value && value !== episodeId.value) {
    episodeId.value = value;
    loadGallery();
  }
});

async function loadGallery() {
  if (!episodeId.value) return;
  error.value = "";
  try {
    gallery.value = await api.gallery(episodeId.value);
  } catch (e) {
    error.value = e.message;
  }
}

async function generateAll() {
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    const r = await api.generateAll(episodeId.value, { variations: 2 });
    notice.value = `已排队 ${r.created.length} 个分镜的生成任务（跳过 ${r.skipped} 个）。每张约 10 分钟，请耐心等待。`;
    await loadGallery();
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}

async function regenerate(shot) {
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    await api.generateShot(shot.shot_id, { variations: 2 });
    notice.value = `镜头 ${shot.shot_index} 已加入生成队列。`;
    await loadGallery();
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}

async function select(image) {
  error.value = "";
  try {
    await api.selectImage(image.id);
    await loadGallery();
  } catch (e) {
    error.value = e.message;
  }
}

// ---------- Sprint 6.5：Prompt 编辑与重新生成 ----------

async function openEditor(shot) {
  if (editShotId.value === shot.shot_id) {
    editShotId.value = null; // 取消编辑
    return;
  }
  promptError.value = "";
  try {
    const [d, ctx] = await Promise.all([
      api.getShotPrompt(shot.shot_id),
      api.generationContext(shot.shot_id),
    ]);
    promptDraft.value = {
      prompt: d.prompt,
      negative_prompt: d.negative_prompt,
      is_custom: d.is_custom,
    };
    refOptions.value = {
      characters: (ctx.characters || []).filter((c) => c.reference_asset_id),
      scene: ctx.scene && ctx.scene.reference_asset_id ? ctx.scene : null,
    };
    // 默认全部勾选（与自动生成行为一致）
    refSelected.value = [
      ...refOptions.value.characters.map((c) => c.reference_asset_id),
      ...(refOptions.value.scene ? [refOptions.value.scene.reference_asset_id] : []),
    ];
    editShotId.value = shot.shot_id;
  } catch (e) {
    error.value = e.message;
  }
}

async function savePrompt(shot) {
  promptSaving.value = true;
  promptError.value = "";
  try {
    const d = await api.saveShotPrompt(shot.shot_id, {
      prompt: promptDraft.value.prompt,
      negative_prompt: promptDraft.value.negative_prompt,
    });
    promptDraft.value.is_custom = d.is_custom;
    notice.value = `镜头 ${shot.shot_index} 的 Prompt 已保存（不会创建新版本）。`;
  } catch (e) {
    promptError.value = e.message; // 保存失败时显示错误
  } finally {
    promptSaving.value = false;
  }
}

async function regenerateCustom(shot) {
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    const [w, h] = regenParams.value.size.split("x").map(Number);
    const charIds = refOptions.value.characters
      .map((c) => c.reference_asset_id)
      .filter((id) => refSelected.value.includes(id));
    const sceneIds =
      refOptions.value.scene &&
      refSelected.value.includes(refOptions.value.scene.reference_asset_id)
        ? [refOptions.value.scene.reference_asset_id]
        : [];
    await api.regenerateShot(shot.shot_id, {
      prompt: promptDraft.value.prompt,
      negative_prompt: promptDraft.value.negative_prompt,
      seed: regenParams.value.seed === "" ? null : Number(regenParams.value.seed),
      steps: regenParams.value.steps,
      variations: regenParams.value.variations,
      width: w,
      height: h,
      character_reference_ids: charIds,
      scene_reference_ids: sceneIds,
    });
    notice.value = `镜头 ${shot.shot_index} 已加入生成队列，新图将创建新版本，不会替换已定稿图片。`;
    editShotId.value = null;
    await loadGallery();
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}

function setupPoll() {
  clearInterval(pollTimer);
  pollTimer = setInterval(() => {
    if (hasActive.value) loadGallery();
  }, 2000);
}

// ---------- Sprint 6.3：图片对比 ----------

function toggleCompare(img) {
  const i = comparePair.value.findIndex((x) => x.id === img.id);
  if (i >= 0) {
    comparePair.value.splice(i, 1);
  } else {
    if (comparePair.value.length >= 2) comparePair.value.shift();
    comparePair.value.push(img);
  }
  if (comparePair.value.length === 2) showCompare.value = true;
}

async function retryJob(shot) {
  busy.value = true;
  error.value = "";
  try {
    await api.retryJob(shot.last_job_id);
    notice.value = `镜头 ${shot.shot_index} 的失败任务已重新排队。`;
    await loadGallery();
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}

function fmtTime(t) {
  if (!t) return "";
  return new Date(t).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

onMounted(() => {
  loadEpisodes();
  setupPoll();
});
onBeforeUnmount(() => clearInterval(pollTimer));
</script>

<template>
  <div>
    <h2>分镜画廊</h2>
    <p class="muted">
      查看每个镜头的候选图，选出最终版本。角色一致性由 Omni 参考图自动锁定。
    </p>

    <div class="panel">
      <label class="muted">选择剧集</label>
      <div style="display: flex; gap: 12px; margin-top: 8px">
        <select v-model="episodeId" @change="changeEpisode" style="flex: 1">
          <option v-for="e in episodes" :key="e.id" :value="e.id">
            第 {{ e.episode_number }} 集 · {{ e.title }}
          </option>
        </select>
        <button class="btn primary" :disabled="busy || !episodeId" @click="generateAll">
          整集生成（每镜头 2 候选）
        </button>
      </div>
      <p v-if="hasActive" class="muted" style="margin-bottom: 0">
        有任务正在生成，进度每 2 秒自动刷新…
      </p>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="notice" class="muted">{{ notice }}</p>

    <div v-if="gallery" class="shot-list">
      <div v-for="s in gallery.shots" :key="s.shot_id" class="shot-card">
        <div class="shot-head">
          <h3>镜头 {{ s.shot_index }}</h3>
          <span v-if="s.active_job" class="badge running">
            {{ STATUS_LABEL[s.active_job.status] }} · {{ s.active_job.progress }}%
          </span>
          <span
            v-else-if="s.last_job_status && s.last_job_status !== 'completed'"
            class="badge unresolved"
          >
            {{ STATUS_LABEL[s.last_job_status] }}
          </span>
          <span v-if="s.images.some((i) => i.is_selected)" class="badge linked">
            已定稿
          </span>
        </div>
        <p class="desc">{{ s.description }}</p>
        <div v-if="s.active_job" class="shot-progress">
          <div class="shot-progress-meta">
            <span>{{ s.active_job.progress_message || '等待生成资源' }}</span>
            <strong>{{ s.active_job.progress }}%</strong>
          </div>
          <div class="shot-progress-track" role="progressbar" :aria-valuenow="s.active_job.progress" aria-valuemin="0" aria-valuemax="100">
            <div :style="{ width: `${s.active_job.progress}%` }"></div>
          </div>
        </div>
        <p class="muted small" v-if="s.camera">🎥 {{ s.camera }}</p>
        <div v-if="s.last_job_status === 'failed' && !s.active_job" class="fail-box">
          <p class="error small">❌ 上次生成失败：{{ s.last_job_error }}</p>
          <button class="ghost" :disabled="busy" @click="retryJob(s)">重试</button>
        </div>

        <div class="img-row" v-if="s.images.length">
          <div
            v-for="img in s.images"
            :key="img.id"
            class="img-box"
            :class="{ selected: img.is_selected }"
          >
            <span class="ver">v{{ img.version ?? img.variation_index }}</span>
            <label class="cmp-check" title="加入对比">
              <input
                type="checkbox"
                :checked="comparePair.some((x) => x.id === img.id)"
                @change="toggleCompare(img)"
              />
              对比
            </label>
            <img
              :src="api.assetFileUrl(img.asset_id)"
              :alt="`v${img.version ?? img.variation_index}`"
              :title="img.prompt"
              loading="lazy"
              @click="compareImg = img"
            />
            <div class="img-meta muted">
              {{ img.width }}×{{ img.height }} · seed {{ img.seed }} ·
              {{ img.steps }} 步 · {{ fmtTime(img.created_at) }}
            </div>
            <div class="img-actions">
              <button
                v-if="!img.is_selected"
                class="ghost"
                @click="select(img)"
              >
                定为最终
              </button>
              <span v-else class="star">✅ 最终版</span>
            </div>
          </div>
        </div>
        <p v-else class="muted small">还没有候选图</p>

        <div class="shot-actions">
          <button
            class="ghost"
            :disabled="busy || !!s.active_job"
            @click="regenerate(s)"
          >
            {{ s.images.length ? "重新生成" : "开始生成" }}
          </button>
          <button class="ghost" @click="openEditor(s)">
            {{ editShotId === s.shot_id ? "取消编辑" : "⚙️ Prompt / 重新生成" }}
          </button>
        </div>

        <div v-if="editShotId === s.shot_id" class="prompt-editor">
          <label class="muted small">
            Prompt
            <span v-if="promptDraft.is_custom" class="badge merge">已自定义</span>
          </label>
          <textarea v-model="promptDraft.prompt" rows="5"></textarea>
          <label class="muted small">Negative Prompt</label>
          <textarea v-model="promptDraft.negative_prompt" rows="2"></textarea>

          <div v-if="refOptions.characters.length || refOptions.scene" class="ref-row">
            <span class="muted small">参考素材（当前模型限制：多张时仅生效第一张角色图）：</span>
            <label v-for="c in refOptions.characters" :key="c.reference_asset_id" class="ref-chip">
              <input type="checkbox" :value="c.reference_asset_id" v-model="refSelected" />
              角色·{{ c.name }}
            </label>
            <label v-if="refOptions.scene" class="ref-chip">
              <input type="checkbox" :value="refOptions.scene.reference_asset_id" v-model="refSelected" />
              场景·{{ refOptions.scene.name }}
            </label>
          </div>

          <div class="param-row">
            <label>Seed
              <input type="text" v-model="regenParams.seed" placeholder="随机" style="width: 90px" />
            </label>
            <label>步数
              <select v-model="regenParams.steps">
                <option :value="4">4</option>
                <option :value="6">6</option>
                <option :value="8">8</option>
              </select>
            </label>
            <label>分辨率
              <select v-model="regenParams.size">
                <option value="1024x576">1024×576 (16:9)</option>
                <option value="1024x1024">1024×1024 (1:1)</option>
                <option value="768x1024">768×1024 (竖版)</option>
              </select>
            </label>
            <label>候选数
              <select v-model="regenParams.variations">
                <option :value="1">1</option>
                <option :value="2">2</option>
              </select>
            </label>
            <label>模型
              <select disabled>
                <option>Z-Image-Turbo bf16</option>
              </select>
            </label>
          </div>

          <p v-if="promptError" class="error">{{ promptError }}</p>
          <div class="row" style="display: flex; gap: 10px; margin-top: 12px">
            <button class="ghost" :disabled="promptSaving" @click="savePrompt(s)">
              {{ promptSaving ? "保存中…" : "保存 Prompt" }}
            </button>
            <button :disabled="busy || !!s.active_job" @click="regenerateCustom(s)">
              按此 Prompt 重新生成
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showCompare && comparePair.length === 2" class="modal-mask" @click.self="showCompare = false">
      <div class="modal" style="width: 1100px">
        <h3>版本对比</h3>
        <div class="compare-grid">
          <div v-for="img in comparePair" :key="img.id" class="compare-col">
            <h4>v{{ img.version ?? img.variation_index }}
              <span v-if="img.is_selected" class="badge linked">当前定稿</span>
            </h4>
            <img :src="api.assetFileUrl(img.asset_id)" class="compare-img" />
            <table class="meta-table">
              <tr><td>分辨率</td><td>{{ img.width }}×{{ img.height }}</td></tr>
              <tr><td>Seed</td><td>{{ img.seed }}</td></tr>
              <tr><td>步数</td><td>{{ img.steps }}</td></tr>
              <tr><td>模型</td><td>{{ img.generation_model || "-" }}</td></tr>
              <tr><td>角色参考</td><td>{{ img.character_reference_asset_ids.length }} 张</td></tr>
              <tr><td>场景参考</td><td>{{ img.scene_reference_asset_ids.length }} 张</td></tr>
              <tr><td>时间</td><td>{{ fmtTime(img.created_at) }}</td></tr>
            </table>
            <details>
              <summary class="muted small">Prompt</summary>
              <p class="small muted prompt-full">{{ img.prompt }}</p>
            </details>
            <button v-if="!img.is_selected" @click="select(img)">定稿此版本</button>
          </div>
        </div>
        <div class="row">
          <button class="ghost" @click="showCompare = false; comparePair = []">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="compareImg" class="modal-mask" @click.self="compareImg = null">
      <div class="modal" style="width: 860px">
        <h3>候选图 {{ compareImg.variation_index }}</h3>
        <img
          :src="api.assetFileUrl(compareImg.asset_id)"
          style="width: 100%; border-radius: 8px"
        />
        <div class="row">
          <button v-if="!compareImg.is_selected" @click="select(compareImg); compareImg = null">
            定为最终
          </button>
          <button class="ghost" @click="compareImg = null">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.shot-list {
  display: flex;
  flex-direction: column;
  gap: 20px;
  margin-top: 20px;
}

.shot-card {
  background: #1c2230;
  border-radius: 14px;
  padding: 20px;
}

.shot-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.shot-head h3 {
  margin: 0;
}

.badge.running {
  background: #713f12;
  color: #fde047;
}

.desc {
  margin: 10px 0 4px;
}

.shot-progress {
  max-width: 640px;
  margin: 14px 0;
}

.shot-progress-meta {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  color: #d4d4d8;
  font-size: 13px;
  margin-bottom: 7px;
}

.shot-progress-meta strong {
  color: #fde047;
}

.shot-progress-track {
  height: 6px;
  border-radius: 999px;
  background: #30384a;
  overflow: hidden;
}

.shot-progress-track div {
  height: 100%;
  background: #eab308;
  transition: width 240ms ease-out;
}

.small {
  font-size: 13px;
  margin: 4px 0;
}

.img-row {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 12px;
}

.img-box {
  width: 300px;
  border: 2px solid transparent;
  border-radius: 10px;
  overflow: hidden;
  position: relative;
}

.ver {
  position: absolute;
  top: 6px;
  left: 6px;
  z-index: 1;
  background: rgba(0, 0, 0, 0.65);
  color: #a5b4fc;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 6px;
}

.img-box.selected {
  border-color: #4ade80;
}

.img-box img {
  width: 100%;
  display: block;
  cursor: zoom-in;
  background: #292f3d;
}

.img-actions {
  display: flex;
  justify-content: center;
  padding: 8px;
}

.star {
  color: #4ade80;
  font-size: 13px;
}

.shot-actions {
  margin-top: 12px;
  display: flex;
  gap: 10px;
}

.img-meta {
  font-size: 11px;
  padding: 4px 8px 0;
}

.cmp-check {
  position: absolute;
  top: 6px;
  right: 6px;
  z-index: 1;
  background: rgba(0, 0, 0, 0.65);
  color: #a1a1aa;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
}

.fail-box {
  background: rgba(127, 29, 29, 0.25);
  border: 1px solid #7f1d1d;
  border-radius: 8px;
  padding: 10px 12px;
  margin-top: 10px;
}

.fail-box .small {
  margin: 0 0 8px;
}

.ref-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.ref-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #a5b4fc;
  background: #292f3d;
  padding: 4px 10px;
  border-radius: 999px;
  cursor: pointer;
}

.compare-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.compare-img {
  width: 100%;
  border-radius: 8px;
}

.meta-table {
  width: 100%;
  font-size: 12px;
  color: #a1a1aa;
  margin: 10px 0;
  border-collapse: collapse;
}

.meta-table td {
  padding: 3px 6px;
  border-bottom: 1px solid #262e40;
}

.meta-table td:first-child {
  width: 70px;
  color: #6b7280;
}

.prompt-full {
  max-height: 120px;
  overflow-y: auto;
  word-break: break-all;
}

.prompt-editor {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid #262e40;
}

.prompt-editor textarea {
  width: 100%;
  min-height: 60px;
  font-size: 13px;
}

.prompt-editor label {
  display: block;
  margin: 10px 0 6px;
}

.param-row {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.param-row label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #a1a1aa;
  margin: 0;
}
</style>
