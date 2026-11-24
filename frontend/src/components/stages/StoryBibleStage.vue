<script setup>
import { computed, ref, watch } from 'vue';
import { api } from '../../services/api';
import SvgIcon from '../SvgIcon.vue';

const props = defineProps({ projectId: String, state: Object });
const emit = defineEmits(['refresh', 'error']);
const emptyBible = () => ({ title: '', genre: '', target_audience: '', world_rules: [], character_profiles: [{ name: '', role: '主角', profile: '', personality: '', development: '' }], main_storyline: '', core_satisfactions: [], dramatic_turning_points: [], narrative_constraints: [] });
const bible = ref(emptyBible()); const suggestions = ref([]); const originalText = ref(''); const sourceDocument = ref(null); const busy = ref(false); const uploading = ref(false); const saved = ref(false);
const protagonist = computed(() => bible.value.character_profiles[0]);
watch(() => props.state, s => {
  const incoming = JSON.parse(JSON.stringify(s?.content?.story_bible || {}));
  const existing = incoming.character_profiles?.find(c => c.role === '主角') || incoming.character_profiles?.[0];
  bible.value = { ...emptyBible(), ...incoming, character_profiles: [{ name: '', role: '主角', profile: '', personality: '', development: '', ...(existing || {}) }] };
  originalText.value = s?.content?.original_text || '';
  sourceDocument.value = s?.content?.source_document || null;
  suggestions.value = s?.content?.suggestions || [];
}, { immediate: true });
const completion = computed(() => [bible.value.title, bible.value.genre, bible.value.main_storyline, protagonist.value?.name, bible.value.core_satisfactions?.length].filter(Boolean).length);
function listText(key) { return Array.isArray(bible.value[key]) ? bible.value[key].join('\n') : bible.value[key] || ''; }
function setList(key, value) { bible.value[key] = value.split('\n').map(v => v.trim()).filter(Boolean); saved.value = false; }
async function save() {
  try { const result = await api.saveStage(props.projectId, 1, { story_bible: bible.value, original_text: originalText.value, source_document: sourceDocument.value, suggestions: suggestions.value }); saved.value = true; return result; }
  catch (e) { emit('error', e.message); throw e; }
}
async function suggest() { busy.value = true; try { await save(); await api.generateStage(props.projectId, 1); emit('refresh'); } catch (e) { emit('error', e.message); } finally { busy.value = false; } }
async function uploadDocument(event) {
  const file = event.target.files[0]; if (!file) return;
  if ((originalText.value || bible.value.title) && !window.confirm('上传新文档会生成一个新版本，当前版本仍保留在历史记录中。是否继续？')) { event.target.value = ''; return; }
  uploading.value = true;
  try { await api.uploadStoryBible(props.projectId, file); saved.value = true; emit('refresh'); }
  catch (e) { emit('error', e.message); }
  finally { uploading.value = false; event.target.value = ''; }
}
defineExpose({ save });
</script>

<template>
  <div class="bible-layout">
    <section class="bible-editor">
      <div class="editor-intro"><div><span class="eyebrow">YOUR STORY, YOUR DIRECTION</span><h3>先定义你想做的故事</h3><p>这里保留作者的完整设定。下方字段只是创作索引，不会替代或删减原文。</p></div><div class="intro-actions"><label class="btn secondary small upload-button" :class="{ disabled: uploading }"><SvgIcon name="upload" :size="15" />{{ uploading ? '正在读取全文…' : '上传设定文档' }}<input type="file" accept=".txt,.md,.docx,.pdf" :disabled="uploading" @change="uploadDocument" hidden /></label><span class="completion">{{ completion }} / 5 项核心资料</span></div></div>
      <div class="document-note"><SvgIcon name="book" :size="14" /><span v-if="sourceDocument">来源：{{ sourceDocument.name }} · 已完整保存 {{ sourceDocument.character_count?.toLocaleString() || originalText.length }} 字，分段读取 {{ sourceDocument.sections_read || 1 }} 部分</span><span v-else>支持 TXT、Markdown、Word、PDF；完整原文会保留在这里。</span></div>
      <label class="original-field">完整故事设定原文<textarea v-model="originalText" placeholder="粘贴或上传作者的完整设定。所有细节、人物关系、世界规则、剧情安排都会原样保留在这里，不因结构化显示而丢失。" @input="saved = false"></textarea><small>{{ originalText.length.toLocaleString() }} 字 · 可直接修改，AI 剧集规划会参考这份完整设定。</small></label>
      <div class="section-divider"><span>创作索引</span><p>用于快速查看和 AI 检索，可随时修改。</p></div>
      <div class="form-grid three"><label>故事名称<input v-model="bible.title" placeholder="例如：都市仙帝归来" @input="saved = false" /></label><label>题材类型<input v-model="bible.genre" placeholder="都市修仙 / 逆袭 / 甜宠" @input="saved = false" /></label><label>目标观众<input v-model="bible.target_audience" placeholder="例如：18–30 岁爽文用户" @input="saved = false" /></label></div>
      <label class="main-field">故事大致走向<textarea v-model="bible.main_storyline" class="storyline" placeholder="概括整个故事的主线和结局方向；完整细节仍以上方原文为准。" @input="saved = false"></textarea></label>
      <div class="form-grid"><label>核心爽点<textarea :value="listText('core_satisfactions')" placeholder="每行一个核心爽点" @change="setList('core_satisfactions', $event.target.value)"></textarea></label><label>世界观与规则<textarea :value="listText('world_rules')" placeholder="每行一条世界规则" @change="setList('world_rules', $event.target.value)"></textarea></label></div>
      <div class="character-heading"><div><h4>主角设定</h4><p>这里只确定主角。其他角色在「资产管理」中根据剧本统一提取。</p></div></div>
      <article class="character-card"><div class="form-grid character-name"><label>主角姓名<input v-model="protagonist.name" placeholder="主角姓名" /></label><label>身份与目标<input v-model="protagonist.profile" placeholder="身份背景、当前处境与目标" /></label></div><div class="form-grid"><label>性格<textarea v-model="protagonist.personality" placeholder="行为方式与性格反差"></textarea></label><label>成长或变化<textarea v-model="protagonist.development" placeholder="主角在故事中的变化"></textarea></label></div></article>
      <div class="form-grid"><label>关键转折<textarea :value="listText('dramatic_turning_points')" placeholder="每行一个预期转折" @change="setList('dramatic_turning_points', $event.target.value)"></textarea></label><label>创作边界<textarea :value="listText('narrative_constraints')" placeholder="每行一条不可违背的设定" @change="setList('narrative_constraints', $event.target.value)"></textarea></label></div>
      <div class="save-row"><span>{{ saved ? '完整原文与创作索引已保存。' : '修改后请保存；审批后仍可退回修改。' }}</span><button class="btn secondary" @click="save"><SvgIcon name="check" :size="16" />保存故事设定</button></div>
    </section>
    <aside class="suggestion-panel"><div class="suggestion-heading"><div class="spark-box"><SvgIcon name="spark" :size="20" /></div><div><h3>AI 设定顾问</h3><p>基于完整设定查漏补缺</p></div></div><button class="btn primary suggest-button" :disabled="busy || uploading" @click="suggest"><SvgIcon name="spark" :size="16" />{{ busy ? '正在思考设定建议…' : suggestions.length ? '重新获取建议' : '获取设定建议' }}</button><div v-if="busy || uploading" class="thinking"><i></i><span>{{ uploading ? '正在分段读取全文并整理创作索引' : '正在检查主角动机、爽点节奏与长线冲突' }}</span></div><div v-else-if="!suggestions.length" class="suggestion-empty"><SvgIcon name="edit" :size="25" /><strong>作者原文始终完整保留</strong><p>AI 建议只补充创作索引，不会删除原文中的设定。</p></div><div v-else class="suggestion-list"><p class="suggestion-note">建议已同步到可编辑索引，请逐项核对。</p><article v-for="(item, index) in suggestions" :key="index"><span>{{ item.category || '设定建议' }}</span><strong>{{ item.issue }}</strong><p>{{ item.suggestion }}</p></article></div></aside>
  </div>
</template>

<style scoped>
.bible-layout{display:grid;grid-template-columns:minmax(0,1fr) 310px;gap:18px;align-items:start}.bible-editor,.suggestion-panel{background:var(--surface);border:1px solid var(--border);border-radius:13px}.bible-editor{padding:25px}.editor-intro{display:flex;justify-content:space-between;gap:16px;margin-bottom:24px}.eyebrow{font-size:9px;letter-spacing:1.3px;color:var(--accent);font-weight:700}.editor-intro h3{font-size:21px;margin:7px 0}.editor-intro p{font-size:12px;color:var(--text-secondary);margin:0;line-height:1.7}.intro-actions{display:flex;align-items:center;gap:9px;align-self:flex-start}.upload-button{cursor:pointer;white-space:nowrap}.upload-button.disabled{opacity:.6;pointer-events:none}.document-note{display:flex;align-items:center;gap:7px;background:var(--page);color:var(--text-tertiary);border-radius:7px;padding:9px 11px;margin:-10px 0 20px;font-size:10px}.completion{white-space:nowrap;background:var(--accent-soft);color:var(--accent);padding:6px 9px;border-radius:99px;font-size:10px}label{display:block;font-size:12px;font-weight:600;margin-bottom:16px}input,textarea{width:100%;margin-top:7px}textarea{min-height:105px;line-height:1.7}label small{display:block;color:var(--text-tertiary);font-weight:400;margin-top:6px}.original-field textarea{min-height:280px;font:13px/1.9 var(--font);background:#fcfcfd}.section-divider{display:flex;align-items:baseline;gap:10px;border-top:1px solid var(--border);padding-top:20px;margin:4px 0 18px}.section-divider span{font-size:14px;font-weight:650}.section-divider p{font-size:11px;color:var(--text-secondary);margin:0}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.form-grid.three{grid-template-columns:repeat(3,1fr)}.main-field .storyline{min-height:130px}.character-heading{border-top:1px solid var(--border);padding-top:20px;margin:7px 0 16px}.character-heading h4{margin:0 0 4px}.character-heading p{margin:0;font-size:11px;color:var(--text-secondary)}.character-card{border:1px solid var(--border);background:#fbfcfd;border-radius:10px;padding:16px;margin-bottom:16px}.character-card label{margin-bottom:10px}.character-card textarea{min-height:70px}.save-row{display:flex;align-items:center;justify-content:space-between;gap:14px;border-top:1px solid var(--border);padding-top:18px}.save-row span{font-size:11px;color:var(--text-secondary)}.suggestion-panel{padding:20px;position:sticky;top:90px}.suggestion-heading{display:flex;align-items:center;gap:11px;margin-bottom:18px}.spark-box{display:grid;place-items:center;width:38px;height:38px;background:var(--accent-soft);color:var(--accent);border-radius:10px}.suggestion-heading h3{font-size:15px;margin:0 0 4px}.suggestion-heading p{font-size:11px;color:var(--text-secondary);margin:0}.suggest-button{width:100%;display:flex;justify-content:center;align-items:center;gap:7px}.suggestion-empty{text-align:center;color:var(--text-secondary);padding:45px 5px 25px}.suggestion-empty strong{display:block;color:var(--text);font-size:13px;margin:13px 0 7px}.suggestion-empty p{font-size:11px;line-height:1.8}.suggestion-note{font-size:11px;color:var(--text-secondary);line-height:1.6}.suggestion-list article{padding:14px 0;border-top:1px solid var(--border)}.suggestion-list article>span{font-size:9px;color:var(--accent);background:var(--accent-soft);padding:3px 6px;border-radius:4px}.suggestion-list strong{display:block;font-size:12px;line-height:1.6;margin:9px 0 5px}.suggestion-list article p{font-size:11px;color:var(--text-secondary);line-height:1.7;margin:0}.thinking{display:flex;align-items:center;gap:10px;font-size:11px;color:var(--text-secondary);padding:24px 0}.thinking i{width:14px;height:14px;border:2px solid var(--accent-soft);border-top-color:var(--accent);border-radius:50%;animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:1100px){.bible-layout{grid-template-columns:1fr}.suggestion-panel{position:static}.form-grid.three{grid-template-columns:1fr 1fr}}@media(max-width:600px){.bible-editor{padding:18px}.form-grid,.form-grid.three{grid-template-columns:1fr;gap:0}.editor-intro{display:block}.intro-actions{margin-top:12px;flex-wrap:wrap}.save-row{align-items:flex-start;flex-direction:column}.save-row .btn{width:100%}}
</style>
