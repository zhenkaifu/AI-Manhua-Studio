<script setup>
import { ref } from "vue";
import { api } from "../services/api";

const props = defineProps({
  projectId: { type: String, required: true },
});

const novel = ref("");
const loading = ref(false);
const confirming = ref(false);
const extraction = ref(null); // { id, draft }
const error = ref("");
const doneMsg = ref("");

async function runExtract() {
  if (!novel.value.trim()) {
    error.value = "请先输入小说内容";
    return;
  }
  loading.value = true;
  error.value = "";
  doneMsg.value = "";
  extraction.value = null;
  try {
    extraction.value = await api.extract(props.projectId, novel.value);
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function confirm() {
  confirming.value = true;
  error.value = "";
  try {
    const r = await api.confirmExtraction(
      extraction.value.id,
      extraction.value.draft
    );
    doneMsg.value =
      `已保存：新建角色 ${r.created_characters.length} 个，` +
      `合并角色 ${r.merged_characters.length} 个，` +
      `新建场景 ${r.created_scenes.length} 个，` +
      `合并场景 ${r.merged_scenes.length} 个。`;
    extraction.value = null;
    novel.value = "";
  } catch (e) {
    error.value = e.message;
  } finally {
    confirming.value = false;
  }
}

const MATCH_LABEL = {
  exact: "已匹配已有档案",
  semantic: "疑似同一对象",
  new: "新发现",
};
</script>

<template>
  <h2>AI 提取</h2>
  <p class="muted">
    从小说中自动识别角色和场景。AI 只做草稿，确认后才会写入档案——同名角色会自动合并而不是重复创建。
  </p>

  <section class="panel">
    <textarea v-model="novel" placeholder="粘贴一段小说，AI 会识别其中的角色和场景..." />
    <br /><br />
    <button @click="runExtract" :disabled="loading">
      {{ loading ? "AI 正在阅读小说..." : "开始提取" }}
    </button>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="doneMsg" style="color: #86efac">{{ doneMsg }}</p>
  </section>

  <section v-if="extraction" class="panel">
    <h3>审核提取结果</h3>

    <template v-if="extraction.draft.characters.length">
      <h4>角色（{{ extraction.draft.characters.length }}）</h4>
      <div
        v-for="(c, i) in extraction.draft.characters"
        :key="'c' + i"
        class="card"
        style="margin-bottom: 12px"
      >
        <p style="margin: 0 0 8px">
          <input type="text" v-model="c.name" style="width: 200px" />
          <span
            class="badge"
            :class="{ merge: c.match_level !== 'new' }"
            style="margin-left: 10px"
          >
            {{ MATCH_LABEL[c.match_level]
            }}<template v-if="c.target_name">：{{ c.target_name }}</template>
          </span>
          <span class="badge" style="margin-left: 6px">
            置信度 {{ Math.round((c.confidence ?? 0) * 100) }}%
          </span>
        </p>
        <p class="muted" style="font-size: 13px; margin: 4px 0">
          外貌：{{ c.appearance || "（未提及）" }}
        </p>
        <p class="muted" style="font-size: 13px; margin: 4px 0">
          原文依据：{{ c.evidence || "（无）" }}
        </p>
        <label class="muted" style="font-size: 13px">
          处理方式：
          <select v-model="c.decision">
            <option value="create">创建新角色</option>
            <option value="merge" :disabled="!c.target_id">
              合并到已有角色
            </option>
            <option value="skip">忽略</option>
          </select>
        </label>
      </div>
    </template>

    <template v-if="extraction.draft.scenes.length">
      <h4>场景（{{ extraction.draft.scenes.length }}）</h4>
      <div
        v-for="(s, i) in extraction.draft.scenes"
        :key="'s' + i"
        class="card"
        style="margin-bottom: 12px"
      >
        <p style="margin: 0 0 8px">
          <input type="text" v-model="s.name" style="width: 200px" />
          <span
            class="badge"
            :class="{ merge: s.match_level !== 'new' }"
            style="margin-left: 10px"
          >
            {{ MATCH_LABEL[s.match_level]
            }}<template v-if="s.target_name">：{{ s.target_name }}</template>
          </span>
        </p>
        <p class="muted" style="font-size: 13px; margin: 4px 0">
          环境：{{ s.environment || "（未提及）" }}
        </p>
        <p class="muted" style="font-size: 13px; margin: 4px 0">
          原文依据：{{ s.evidence || "（无）" }}
        </p>
        <label class="muted" style="font-size: 13px">
          处理方式：
          <select v-model="s.decision">
            <option value="create">创建新场景</option>
            <option value="merge" :disabled="!s.target_id">
              合并到已有场景
            </option>
            <option value="skip">忽略</option>
          </select>
        </label>
      </div>
    </template>

    <p v-if="!extraction.draft.characters.length && !extraction.draft.scenes.length" class="muted">
      AI 没有在这段小说中发现明确的角色或场景。
    </p>

    <button
      v-if="extraction.draft.characters.length || extraction.draft.scenes.length"
      @click="confirm"
      :disabled="confirming"
    >
      {{ confirming ? "保存中..." : "确认并保存到档案" }}
    </button>
  </section>
</template>
