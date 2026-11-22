<script setup>
import { onMounted, ref } from "vue";
import { api } from "../services/api";

const props = defineProps({
  projectId: { type: String, required: true },
});

const assets = ref([]);
const error = ref("");

async function load() {
  try {
    assets.value = await api.listAssets(props.projectId);
  } catch (e) {
    error.value = e.message;
  }
}

async function remove(a) {
  if (!window.confirm("确定删除这张图片吗？关联的角色/场景会失去参考图。")) return;
  await api.deleteAsset(a.id);
  load();
}

const TYPE_LABEL = {
  character_reference: "角色参考图",
  scene_reference: "场景参考图",
};

onMounted(load);
</script>

<template>
  <h2>资产库</h2>
  <p class="muted">所有参考图片。图片保存在本地文件系统，数据库只记录路径。</p>

  <p v-if="error" class="error">{{ error }}</p>
  <p v-if="!assets.length" class="muted" style="margin-top: 16px">
    还没有图片。在角色或场景的编辑器里上传参考图后会出现在这里。
  </p>

  <div class="grid">
    <div class="card" v-for="a in assets" :key="a.id">
      <img class="ref" :src="api.assetFileUrl(a.id)" :alt="a.id" />
      <p style="margin: 10px 0 4px">
        <span class="badge">{{ TYPE_LABEL[a.asset_type] || a.asset_type }}</span>
      </p>
      <p class="muted" style="font-size: 13px">
        {{ a.width }}×{{ a.height }} · {{ a.mime_type }}
      </p>
      <div class="actions">
        <button class="danger" @click="remove(a)">删除</button>
      </div>
    </div>
  </div>
</template>
