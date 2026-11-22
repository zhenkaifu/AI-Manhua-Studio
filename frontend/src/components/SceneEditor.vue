<script setup>
import { reactive, ref } from "vue";
import { api } from "../services/api";

const props = defineProps({
  projectId: { type: String, required: true },
  scene: { type: Object, default: null },
});
const emit = defineEmits(["saved", "close"]);

const isEdit = !!props.scene;
const form = reactive({
  name: props.scene?.name ?? "",
  aliasesText: (props.scene?.aliases ?? []).join("、"),
  location_type: props.scene?.location_type ?? "indoor",
  environment: props.scene?.environment ?? "",
  architecture: props.scene?.architecture ?? "",
  lighting: props.scene?.lighting ?? "",
  atmosphere: props.scene?.atmosphere ?? "",
  visual_prompt: props.scene?.visual_prompt ?? "",
  status: props.scene?.status ?? "draft",
});

const saving = ref(false);
const error = ref("");
const refFile = ref(null);

function onFile(e) {
  refFile.value = e.target.files[0] || null;
}

async function save() {
  if (!form.name.trim()) {
    error.value = "场景名称不能为空";
    return;
  }
  saving.value = true;
  error.value = "";
  const payload = {
    name: form.name.trim(),
    aliases: form.aliasesText
      .split(/[、,，]/)
      .map((s) => s.trim())
      .filter(Boolean),
    location_type: form.location_type || null,
    environment: form.environment || null,
    architecture: form.architecture || null,
    lighting: form.lighting || null,
    atmosphere: form.atmosphere || null,
    visual_prompt: form.visual_prompt || null,
    status: form.status,
  };
  try {
    let saved;
    if (isEdit) {
      saved = await api.updateScene(props.scene.id, payload);
    } else {
      saved = await api.createScene(props.projectId, payload);
    }
    if (refFile.value) {
      await api.uploadSceneRef(saved.id, refFile.value);
    }
    emit("saved");
  } catch (e) {
    error.value = e.message;
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="modal-mask" @click.self="emit('close')">
    <div class="modal">
      <h2>{{ isEdit ? "编辑场景" : "新建场景" }}</h2>

      <label>名称 *</label>
      <input type="text" v-model="form.name" />

      <label>别名（用、分隔）</label>
      <input type="text" v-model="form.aliasesText" />

      <label>类型</label>
      <select v-model="form.location_type">
        <option value="indoor">室内</option>
        <option value="outdoor">室外</option>
      </select>

      <label>环境描述</label>
      <textarea v-model="form.environment" />

      <label>建筑风格</label>
      <input type="text" v-model="form.architecture" />

      <label>光照</label>
      <input type="text" v-model="form.lighting" />

      <label>氛围</label>
      <input type="text" v-model="form.atmosphere" />

      <label>视觉 Prompt（英文，供图片生成）</label>
      <textarea v-model="form.visual_prompt" />

      <label>状态</label>
      <select v-model="form.status">
        <option value="draft">draft（草稿）</option>
        <option value="approved">approved（已审核）</option>
      </select>

      <label>参考图片（PNG / JPG / WebP，≤10MB）</label>
      <input type="file" accept="image/png,image/jpeg,image/webp" @change="onFile" />

      <p v-if="error" class="error">{{ error }}</p>

      <div class="row">
        <button class="ghost" @click="emit('close')">取消</button>
        <button @click="save" :disabled="saving">
          {{ saving ? "保存中..." : "保存" }}
        </button>
      </div>
    </div>
  </div>
</template>
