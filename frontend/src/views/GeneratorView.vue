<script setup>
import { ref } from "vue";
import { api } from "../services/api";

const novel = ref("");
const loading = ref(false);
const result = ref(null);
const error = ref("");

async function generate() {
  if (!novel.value.trim()) {
    error.value = "请先输入小说内容";
    return;
  }
  loading.value = true;
  error.value = "";
  result.value = null;
  try {
    result.value = await api.generate(novel.value);
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <h2>剧本生成</h2>
  <p class="muted">粘贴小说，由本地 Qwen3 生成一集 1–3 分钟国漫的结构化剧本和分镜。</p>

  <section class="panel">
    <textarea v-model="novel" placeholder="在这里粘贴你的小说内容..." />
    <br /><br />
    <button @click="generate" :disabled="loading">
      {{ loading ? "AI 正在创作..." : "生成第一集" }}
    </button>
    <p v-if="error" class="error">{{ error }}</p>
  </section>

  <section v-if="result" class="panel">
    <h2>{{ result.episode.title }}</h2>
    <p>{{ result.episode.summary }}</p>
    <p>
      <span class="badge">镜头 {{ result.shots }} 个</span>
      <span class="badge" style="margin-left: 8px">
        总时长 {{ result.duration }} 秒
      </span>
    </p>

    <h3>人物设定</h3>
    <div v-for="c in result.episode.characters" :key="c.id">
      <strong>{{ c.name }}</strong>
      <p class="muted">{{ c.appearance }}</p>
    </div>

    <h3>分镜列表</h3>
    <article
      v-for="shot in result.episode.shots"
      :key="shot.id"
      style="border-top: 1px solid #41495b; padding: 14px 0"
    >
      <strong>镜头 {{ shot.id }} · {{ shot.duration }} 秒 · {{ shot.camera }}</strong>
      <p>{{ shot.scene }}</p>
      <p>{{ shot.action }}</p>
      <p v-if="shot.dialogue">「{{ shot.dialogue }}」</p>
      <p class="muted" style="font-size: 13px">{{ shot.visual_prompt }}</p>
    </article>
  </section>
</template>
