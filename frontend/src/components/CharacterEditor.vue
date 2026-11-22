<script setup>
import { reactive, ref } from "vue";
import { api } from "../services/api";

const props = defineProps({
  projectId: { type: String, required: true },
  character: { type: Object, default: null }, // null = 新建
});
const emit = defineEmits(["saved", "close"]);

const isEdit = !!props.character;
const form = reactive({
  name: props.character?.name ?? "",
  aliasesText: (props.character?.aliases ?? []).join("、"),
  age_description: props.character?.age_description ?? "",
  appearance: props.character?.appearance ?? "",
  hairstyle: props.character?.hairstyle ?? "",
  clothing: props.character?.clothing ?? "",
  personality: props.character?.personality ?? "",
  voice_style: props.character?.voice_style ?? "",
  visual_prompt: props.character?.visual_prompt ?? "",
  negative_prompt: props.character?.negative_prompt ?? "",
  status: props.character?.status ?? "draft",
});

const saving = ref(false);
const error = ref("");
const refFile = ref(null);

function onFile(e) {
  refFile.value = e.target.files[0] || null;
}

async function save() {
  if (!form.name.trim()) {
    error.value = "角色名字不能为空";
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
    age_description: form.age_description || null,
    appearance: form.appearance || null,
    hairstyle: form.hairstyle || null,
    clothing: form.clothing || null,
    personality: form.personality || null,
    voice_style: form.voice_style || null,
    visual_prompt: form.visual_prompt || null,
    negative_prompt: form.negative_prompt || null,
    status: form.status,
  };
  try {
    let saved;
    if (isEdit) {
      saved = await api.updateCharacter(props.character.id, payload);
    } else {
      saved = await api.createCharacter(props.projectId, payload);
    }
    if (refFile.value) {
      await api.uploadCharacterRef(saved.id, refFile.value);
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
      <h2>{{ isEdit ? "编辑角色" : "新建角色" }}</h2>

      <label>名字 *</label>
      <input type="text" v-model="form.name" />

      <label>别名（用、分隔）</label>
      <input type="text" v-model="form.aliasesText" placeholder="例如：枫儿、林公子" />

      <label>年龄描述</label>
      <input type="text" v-model="form.age_description" />

      <label>外貌</label>
      <textarea v-model="form.appearance" />

      <label>发型</label>
      <input type="text" v-model="form.hairstyle" />

      <label>服装</label>
      <input type="text" v-model="form.clothing" />

      <label>性格</label>
      <textarea v-model="form.personality" />

      <label>声音风格</label>
      <input type="text" v-model="form.voice_style" />

      <label>视觉 Prompt（英文，供图片生成）</label>
      <textarea v-model="form.visual_prompt" />

      <label>Negative Prompt</label>
      <textarea v-model="form.negative_prompt" />

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
