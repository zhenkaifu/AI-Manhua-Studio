<script setup>
import { onMounted, ref } from "vue";
import { api } from "../services/api";

const props = defineProps({
  projectId: { type: String, required: true },
});

const episodes = ref([]);
const episodeId = ref("");
const board = ref(null); // /episodes/{id}/entity-links 的结果
const characters = ref([]);
const scenes = ref([]);
const error = ref("");
const notice = ref("");
const linking = ref(false);
const generating = ref(false);
const showGenerate = ref(false);
const novel = ref("");
const contextData = ref(null); // generation-context 弹窗内容

const STATUS_LABEL = {
  linked: "已关联",
  pending: "待确认",
  unresolved: "未识别",
  ignored: "已忽略",
};
const METHOD_LABEL = {
  exact: "名字匹配",
  alias: "别名匹配",
  semantic: "语义匹配",
  manual: "人工",
  none: "",
};

async function loadBase() {
  try {
    [episodes.value, characters.value, scenes.value] = await Promise.all([
      api.listEpisodes(props.projectId),
      api.listCharacters(props.projectId),
      api.listScenes(props.projectId),
    ]);
    if (episodes.value.length && !episodeId.value) {
      episodeId.value = episodes.value[episodes.value.length - 1].id;
      await loadBoard();
    }
  } catch (e) {
    error.value = e.message;
  }
}

async function loadBoard() {
  if (!episodeId.value) return;
  error.value = "";
  try {
    board.value = await api.episodeLinks(episodeId.value);
  } catch (e) {
    error.value = e.message;
  }
}

async function generate() {
  if (!novel.value.trim()) return;
  generating.value = true;
  error.value = "";
  notice.value = "";
  try {
    const ep = await api.generateEpisode(props.projectId, novel.value);
    notice.value = `已生成《${ep.title}》：${ep.shot_count} 个镜头，总时长 ${ep.total_duration} 秒。`;
    novel.value = "";
    showGenerate.value = false;
    await loadBase();
    episodeId.value = ep.id;
    await autoLink();
  } catch (e) {
    error.value = e.message;
  } finally {
    generating.value = false;
  }
}

async function autoLink() {
  if (!episodeId.value) return;
  linking.value = true;
  error.value = "";
  try {
    const r = await api.linkEntities(episodeId.value);
    notice.value = `自动关联完成：已关联 ${r.linked}，待确认 ${r.pending}，未识别 ${r.unresolved}。`;
    await loadBoard();
  } catch (e) {
    error.value = e.message;
  } finally {
    linking.value = false;
  }
}

// 改绑：更新某个 link 的目标后整体 PUT
async function rebind(shot, link, newEntityId) {
  const links = shot.links
    .filter((l) => l.status !== "ignored")
    .map((l) => ({
      entity_type: l.entity_type,
      entity_id: l.id === link.id ? newEntityId || null : l.entity_id,
      mention_text: l.mention_text,
    }));
  try {
    await api.setShotLinks(shot.shot_id, links);
    await loadBoard();
  } catch (e) {
    error.value = e.message;
  }
}

async function resolve(shot, link, action, entityId) {
  try {
    await api.resolveEntity(shot.shot_id, {
      mention_text: link.mention_text,
      entity_type: link.entity_type,
      action,
      entity_id: entityId || null,
    });
    if (action === "create") {
      // 新建的草稿角色/场景要刷新候选列表
      [characters.value, scenes.value] = await Promise.all([
        api.listCharacters(props.projectId),
        api.listScenes(props.projectId),
      ]);
    }
    await loadBoard();
  } catch (e) {
    error.value = e.message;
  }
}

async function showContext(shot) {
  try {
    contextData.value = await api.generationContext(shot.shot_id);
  } catch (e) {
    error.value = e.message;
  }
}

function optionsFor(type) {
  return type === "character" ? characters.value : scenes.value;
}

onMounted(loadBase);
</script>

<template>
  <h2>分镜关联</h2>
  <p class="muted">
    把每个镜头里的角色和场景关联到档案库。关联保存的是 ID，角色改名也不会断。
  </p>

  <section class="panel" style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap">
    <label class="muted">剧集：</label>
    <select v-model="episodeId" @change="loadBoard" style="min-width: 220px">
      <option v-for="e in episodes" :key="e.id" :value="e.id">
        第 {{ e.episode_number }} 集 · {{ e.title }}（{{ e.shot_count }} 镜）
      </option>
    </select>
    <button @click="autoLink" :disabled="!episodeId || linking">
      {{ linking ? "AI 匹配中..." : "自动关联" }}
    </button>
    <button class="ghost" @click="showGenerate = !showGenerate">
      {{ showGenerate ? "收起" : "生成新剧集" }}
    </button>
    <p v-if="notice" style="color: #86efac; width: 100%; margin: 4px 0 0">{{ notice }}</p>
    <p v-if="error" class="error" style="width: 100%; margin: 4px 0 0">{{ error }}</p>
  </section>

  <section v-if="showGenerate" class="panel">
    <h3 style="margin-top: 0">从小说生成新剧集（自动入库并关联）</h3>
    <textarea v-model="novel" placeholder="粘贴小说内容，由 Qwen3 生成分镜..." />
    <br /><br />
    <button @click="generate" :disabled="generating">
      {{ generating ? "AI 创作中（约1分钟）..." : "生成并关联" }}
    </button>
  </section>

  <p v-if="!episodes.length" class="muted">
    这个项目还没有剧集。点击「生成新剧集」从小说创建，或先用「剧本生成」页测试。
  </p>

  <section v-for="shot in board?.shots ?? []" :key="shot.shot_id" class="panel">
    <h3 style="margin-top: 0">
      镜头 {{ shot.shot_index }}
      <span class="badge">{{ shot.duration }} 秒</span>
      <span class="badge" style="margin-left: 6px">{{ shot.camera }}</span>
    </h3>
    <p class="muted" style="margin: 6px 0">{{ shot.scene }}</p>
    <p style="margin: 6px 0">{{ shot.action }}</p>
    <p v-if="shot.dialogue" style="margin: 6px 0">「{{ shot.dialogue }}」</p>

    <div v-for="link in shot.links" :key="link.id" class="link-row">
      <img
        v-if="link.reference_asset_id"
        :src="api.assetFileUrl(link.reference_asset_id)"
        class="thumb"
      />
      <span class="mention">{{ link.mention_text }}</span>
      <span>→</span>

      <template v-if="link.status === 'unresolved'">
        <span class="badge unresolved">未识别</span>
        <select
          :value="''"
          @change="
            $event.target.value === '__create'
              ? resolve(shot, link, 'create')
              : $event.target.value === '__ignore'
                ? resolve(shot, link, 'ignore')
                : resolve(shot, link, 'link', $event.target.value)
          "
        >
          <option value="" disabled>处理…</option>
          <option v-for="o in optionsFor(link.entity_type)" :key="o.id" :value="o.id">
            关联到：{{ o.name }}
          </option>
          <option value="__create">新建草稿{{ link.entity_type === "character" ? "角色" : "场景" }}</option>
          <option value="__ignore">忽略</option>
        </select>
      </template>

      <template v-else>
        <strong>{{ link.entity_name || "（未关联）" }}</strong>
        <span class="badge" :class="link.status">{{ STATUS_LABEL[link.status] }}</span>
        <span class="badge">{{ METHOD_LABEL[link.match_method] }}</span>
        <select
          :value="link.entity_id || ''"
          @change="rebind(shot, link, $event.target.value)"
        >
          <option v-for="o in optionsFor(link.entity_type)" :key="o.id" :value="o.id">
            {{ o.name }}
          </option>
          <option value="">解除关联</option>
        </select>
      </template>
    </div>

    <button class="ghost" style="margin-top: 10px" @click="showContext(shot)">
      查看 Phase 3 生成数据
    </button>
  </section>

  <div v-if="contextData" class="modal-mask" @click.self="contextData = null">
    <div class="modal">
      <h2>Generation Context（镜头 {{ contextData.shot_index }}）</h2>
      <p class="muted">这是 Phase 3 图片生成模块将读取的数据（只读）。</p>
      <pre class="json-view">{{ JSON.stringify(contextData, null, 2) }}</pre>
      <div class="row">
        <button class="ghost" @click="contextData = null">关闭</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.link-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-top: 1px solid #2a3247;
  flex-wrap: wrap;
}

.mention {
  color: #fcd34d;
}

.thumb {
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: 6px;
  background: #292f3d;
}

select {
  max-width: 220px;
}

.json-view {
  background: #10131b;
  padding: 14px;
  border-radius: 8px;
  font-size: 12px;
  max-height: 420px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
