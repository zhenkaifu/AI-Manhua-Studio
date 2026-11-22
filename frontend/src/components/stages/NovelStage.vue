<script setup>
import { computed, ref, watch } from 'vue';
import { api } from '../../services/api';
import SvgIcon from '../SvgIcon.vue';
const props = defineProps({ projectId: String, state: Object });
const emit = defineEmits(['refresh', 'error']);
const text = ref(''); const novelName = ref('未命名小说'); const busy = ref(false); const editing = ref(false); const bibleDraft = ref(''); const activeSection = ref('world_rules');
const novel = computed(() => props.state?.content?.novel || null);
const bible = computed(() => props.state?.content?.story_bible || null);
const sections = [{ key: 'world_rules', label: '世界规则' }, { key: 'character_profiles', label: '角色档案' }, { key: 'relationships', label: '人物关系' }, { key: 'locations', label: '地点与势力' }, { key: 'important_events', label: '重要事件' }, { key: 'timeline', label: '时间线' }, { key: 'narrative_constraints', label: '叙事约束' }];
watch(() => props.state, s => { text.value = s?.content?.novel?.text || ''; novelName.value = s?.content?.novel?.name || '未命名小说'; bibleDraft.value = JSON.stringify(s?.content?.story_bible || {}, null, 2); }, { immediate: true });
async function importText() { if (!text.value.trim()) return emit('error', '请先粘贴小说原文'); busy.value = true; try { await api.importNovel(props.projectId, novelName.value, text.value); emit('refresh'); } catch(e) { emit('error', e.message); } finally { busy.value = false; } }
async function upload(event) { const file = event.target.files[0]; if (!file) return; busy.value = true; try { await api.uploadNovel(props.projectId, file); emit('refresh'); } catch(e) { emit('error', e.message); } finally { busy.value = false; event.target.value = ''; } }
async function analyze() { busy.value = true; try { await api.generateStage(props.projectId, 1); emit('refresh'); } catch(e) { emit('error', e.message); } finally { busy.value = false; } }
async function saveBible() { try { const parsed = JSON.parse(bibleDraft.value); await api.saveStage(props.projectId, 1, { ...props.state.content, story_bible: parsed }); editing.value = false; emit('refresh'); } catch(e) { emit('error', e.message instanceof SyntaxError ? 'JSON 格式不正确' : e.message); } }
function display(value) { return typeof value === 'string' ? value : JSON.stringify(value, null, 2); }
</script>
<template>
  <div class="stage-layout">
    <section v-if="!novel" class="import-panel">
      <div class="import-intro"><div class="feature-icon"><SvgIcon name="book" :size="25" /></div><h2>导入故事原文</h2><p>AI 将分析世界规则、人物关系、重要事件和叙事约束，形成可持续复用的 Story Bible。</p></div>
      <label class="field-label">小说名称<input v-model="novelName" placeholder="输入小说名称" /></label>
      <textarea v-model="text" class="novel-input" placeholder="在这里粘贴小说原文…"></textarea>
      <div class="import-actions"><label class="btn secondary file-button"><SvgIcon name="upload" :size="17" />上传 TXT / DOCX / EPUB<input type="file" accept=".txt,.docx,.epub" @change="upload" hidden /></label><button class="btn primary" :disabled="busy || !text.trim()" @click="importText">{{ busy ? '正在导入…' : '导入并解析章节' }}</button></div>
    </section>
    <template v-else>
      <div class="content-toolbar"><div><strong>{{ novel.name }}</strong><span>{{ novel.chapters.length }} 章 · {{ novel.character_count.toLocaleString() }} 字</span></div><div class="toolbar-actions"><label class="btn secondary small file-button"><SvgIcon name="upload" :size="15" />替换原文<input type="file" accept=".txt,.docx,.epub" @change="upload" hidden /></label><button class="btn primary small" :disabled="busy" @click="analyze"><SvgIcon name="spark" :size="16" />{{ busy ? 'AI 正在分析…' : bible ? '重新分析' : '生成 Story Bible' }}</button></div></div>
      <div class="analysis-grid">
        <aside class="chapter-panel"><div class="panel-title">原文章节<span>{{ novel.chapters.length }}</span></div><details v-for="(chapter, i) in novel.chapters" :key="chapter.id" :open="i === 0"><summary><span>{{ String(i + 1).padStart(2, '0') }}</span>{{ chapter.title }}</summary><p>{{ chapter.content.slice(0, 260) }}{{ chapter.content.length > 260 ? '…' : '' }}</p></details></aside>
        <section class="bible-panel">
          <div v-if="!bible" class="empty-content"><SvgIcon name="spark" :size="28" /><h3>Story Bible 尚未生成</h3><p>原文已准备好。AI 分析完成后，你需要逐项检查并人工审批。</p><button class="btn primary" :disabled="busy" @click="analyze">开始 AI 分析</button></div>
          <template v-else>
            <div class="panel-title"><span>Story Bible</span><button class="btn secondary small" @click="editing = !editing"><SvgIcon name="edit" :size="15" />{{ editing ? '取消编辑' : '编辑 JSON' }}</button></div>
            <div v-if="editing" class="json-editor"><textarea v-model="bibleDraft" spellcheck="false"></textarea><button class="btn primary small" @click="saveBible">保存修改</button></div>
            <template v-else><div class="bible-tabs"><button v-for="item in sections" :key="item.key" :class="{ active: activeSection === item.key }" @click="activeSection = item.key">{{ item.label }}</button></div><div class="bible-content"><template v-if="activeSection === 'locations'"><h3>地点</h3><pre>{{ display(bible.locations || []) }}</pre><h3>势力</h3><pre>{{ display(bible.factions || []) }}</pre></template><pre v-else>{{ display(bible[activeSection] || []) }}</pre><div v-if="activeSection === 'important_events'" class="extra-bible"><h3>伏笔与转折</h3><pre>{{ display({ foreshadowing: bible.foreshadowing, dramatic_turning_points: bible.dramatic_turning_points }) }}</pre></div></div></template>
          </template>
        </section>
      </div>
    </template>
  </div>
</template>
<style scoped>
.import-panel{background:var(--surface);border:1px solid var(--border);border-radius:13px;padding:28px}.import-intro{text-align:center;max-width:540px;margin:0 auto 24px}.feature-icon{width:50px;height:50px;display:grid;place-items:center;margin:0 auto 14px;background:var(--accent-soft);color:var(--accent);border-radius:13px}.import-intro h2{margin:0 0 8px}.import-intro p{color:var(--text-secondary);line-height:1.7}.field-label{font-size:13px;font-weight:600}.field-label input{display:block;width:100%;margin-top:7px}.novel-input{min-height:330px;margin:16px 0;line-height:1.8}.import-actions{display:flex;justify-content:space-between;gap:12px}.file-button{cursor:pointer}.content-toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;background:var(--surface);border:1px solid var(--border);padding:14px 16px;border-radius:11px}.content-toolbar strong{display:block}.content-toolbar span{font-size:12px;color:var(--text-secondary)}.toolbar-actions{display:flex;gap:8px}.analysis-grid{display:grid;grid-template-columns:280px 1fr;gap:16px;min-height:540px}.chapter-panel,.bible-panel{background:var(--surface);border:1px solid var(--border);border-radius:11px;overflow:hidden}.panel-title{display:flex;align-items:center;justify-content:space-between;padding:15px 17px;border-bottom:1px solid var(--border);font-size:14px;font-weight:650}.panel-title>span{color:var(--text-secondary);font-size:12px}.chapter-panel{max-height:650px;overflow:auto}.chapter-panel details{border-bottom:1px solid var(--border-light)}.chapter-panel summary{display:flex;gap:9px;padding:13px 16px;cursor:pointer;font-size:13px}.chapter-panel summary span{color:var(--text-tertiary)}.chapter-panel details p{font-size:12px;line-height:1.7;color:var(--text-secondary);padding:0 16px 14px}.empty-content{text-align:center;padding:100px 30px;color:var(--text-secondary)}.empty-content h3{color:var(--text)}.empty-content p{margin-bottom:20px}.bible-tabs{display:flex;gap:3px;padding:10px 12px;border-bottom:1px solid var(--border);overflow:auto}.bible-tabs button{background:transparent;color:var(--text-secondary);white-space:nowrap;padding:8px 10px;font-size:12px}.bible-tabs button.active{background:var(--accent-soft);color:var(--accent)}.bible-content{padding:20px;max-height:550px;overflow:auto}.bible-content pre{white-space:pre-wrap;word-break:break-word;font:13px/1.8 var(--font);color:var(--text);margin:0}.bible-content h3{font-size:14px;margin:0 0 10px}.extra-bible{margin-top:22px}.json-editor{padding:16px}.json-editor textarea{min-height:430px;font:12px/1.6 monospace}.json-editor button{margin-top:10px}@media(max-width:850px){.analysis-grid{grid-template-columns:1fr}.chapter-panel{max-height:260px}.content-toolbar{align-items:flex-start;gap:12px}.toolbar-actions{flex-wrap:wrap;justify-content:flex-end}}
</style>
