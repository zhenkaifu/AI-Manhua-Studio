<script setup>
import { ref } from 'vue';
import { api } from '../../services/api';
import CharactersView from '../../views/CharactersView.vue';
import ScenesView from '../../views/ScenesView.vue';
import SvgIcon from '../SvgIcon.vue';
const props = defineProps({ projectId: String, state: Object });
const emit = defineEmits(['refresh', 'error']);
const tab = ref('characters'); const checking = ref(false); const quality = ref(null); const propsDraft = ref([...(props.state?.content?.props || [])]);
async function check() { checking.value = true; try { quality.value = await api.reviewStage(props.projectId, 4); } catch(e) { emit('error', e.message); } finally { checking.value = false; } }
function addProp() { propsDraft.value.push({ id: `prop_${Date.now()}`, name: '新道具', description: '', narrative_significance: '' }); }
async function save() { return await api.saveStage(props.projectId, 4, { ...props.state.content, props: propsDraft.value }); }
defineExpose({ save });
</script>
<template>
  <div class="assets-stage">
    <div class="assets-toolbar"><div class="segmented"><button :class="{ active: tab === 'characters' }" @click="tab = 'characters'">角色资产</button><button :class="{ active: tab === 'scenes' }" @click="tab = 'scenes'">场景资产</button><button :class="{ active: tab === 'props' }" @click="tab = 'props'">重要道具</button></div><button class="btn secondary small" :disabled="checking" @click="check"><SvgIcon name="spark" :size="15" />{{ checking ? '检查中…' : '资产完整性检查' }}</button></div>
    <div v-if="quality" class="quality-strip" :class="{ good: !quality.issues.length }"><strong>{{ quality.summary }}</strong><span v-for="(issue, i) in quality.issues" :key="i">{{ issue.issue }} · {{ issue.suggestion }}</span><button @click="quality = null">×</button></div>
    <div class="embedded-assets"><CharactersView v-if="tab === 'characters'" :project-id="projectId" /><ScenesView v-else-if="tab === 'scenes'" :project-id="projectId" /><section v-else class="props-panel"><div class="props-heading"><div><h2>重要道具</h2><p>记录会影响剧情或画面一致性的关键物件。</p></div><button class="btn secondary small" @click="addProp"><SvgIcon name="plus" :size="15" />添加道具</button></div><p v-if="!propsDraft.length" class="muted">还没有登记重要道具。</p><div v-for="(prop, i) in propsDraft" :key="prop.id" class="prop-row"><input v-model="prop.name" placeholder="道具名称" /><input v-model="prop.description" placeholder="外观与材质" /><input v-model="prop.narrative_significance" placeholder="剧情作用" /><button class="icon-btn" @click="propsDraft.splice(i, 1)"><SvgIcon name="trash" :size="16" /></button></div><button v-if="propsDraft.length" class="btn primary small" @click="save">保存道具</button></section></div>
    <p class="asset-note">审批本阶段会锁定当前角色与场景参考图。后续分镜生成会继续使用现有 Entity Linking 和 Generation Context，不会为单个镜头另造人物外观。</p>
  </div>
</template>
<style scoped>
.assets-toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.segmented{display:flex;background:#e9edf2;border-radius:9px;padding:3px}.segmented button{background:transparent;color:var(--text-secondary);padding:8px 15px;font-size:13px}.segmented button.active{background:var(--surface);color:var(--text);box-shadow:0 1px 3px rgba(20,30,50,.08)}.quality-strip{position:relative;display:flex;flex-direction:column;gap:4px;background:#fff7e8;border:1px solid #eed9ac;color:#7c5312;border-radius:9px;padding:12px 35px 12px 14px;margin-bottom:14px;font-size:12px}.quality-strip.good{background:#edf8f2;border-color:#c8e7d6;color:#226543}.quality-strip button{position:absolute;right:10px;top:8px;background:transparent;color:inherit;padding:3px}.embedded-assets :deep(h2){font-size:19px;margin:0}.embedded-assets :deep(.view-heading>p){display:none}.embedded-assets :deep(.grid){grid-template-columns:repeat(auto-fill,minmax(225px,1fr))}.asset-note{font-size:12px;line-height:1.7;color:var(--text-secondary);background:var(--surface);border:1px solid var(--border);padding:12px 14px;border-radius:9px;margin-top:18px}.props-panel{background:var(--surface);border:1px solid var(--border);border-radius:11px;padding:20px}.props-heading{display:flex;justify-content:space-between}.props-heading h2{margin:0}.props-heading p{color:var(--text-secondary);font-size:13px}.prop-row{display:grid;grid-template-columns:180px 1fr 1fr 36px;gap:8px;margin:10px 0}.prop-row input{width:100%}@media(max-width:700px){.prop-row{grid-template-columns:1fr}.assets-toolbar{align-items:flex-start;gap:10px}}
</style>
