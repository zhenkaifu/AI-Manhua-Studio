<script setup>
import { computed, nextTick, ref, watch } from 'vue';
import { api } from '../../services/api';
import SvgIcon from '../SvgIcon.vue';

const props = defineProps({ projectId: String, state: Object });
const emit = defineEmits(['refresh', 'error']);
const novel = ref(null); const selectedId = ref(''); const busy = ref(false); const saving = ref(false); const saved = ref(false); const importOpen = ref(false); const importName = ref('未命名小说'); const importText = ref(''); const editor = ref(null);
const chapters = computed(() => novel.value?.chapters || []);
const selected = computed(() => chapters.value.find(c => c.id === selectedId.value));
const selectedIndex = computed(() => chapters.value.findIndex(c => c.id === selectedId.value));
watch(() => props.state, s => {
  novel.value = JSON.parse(JSON.stringify(s?.content?.novel || null));
  if (!chapters.value.some(c => c.id === selectedId.value)) selectedId.value = chapters.value[0]?.id || '';
}, { immediate: true });
function newId() { return `chapter_${crypto.randomUUID().replaceAll('-', '').slice(0, 16)}`; }
function normalize() {
  if (!novel.value) return;
  novel.value.chapters.forEach(c => { c.paragraphs = (c.content || '').split('\n').map(p => p.trim()).filter(Boolean); });
  novel.value.text = novel.value.chapters.map(c => `${c.title}\n${c.content || ''}`.trim()).join('\n\n');
  novel.value.character_count = novel.value.text.length;
}
async function save(refresh = false) {
  if (!novel.value) return;
  normalize(); saving.value = true;
  try { const result = await api.saveStage(props.projectId, 3, { novel: novel.value }); saved.value = true; if (refresh) emit('refresh'); return result; }
  catch (e) { emit('error', e.message); throw e; }
  finally { saving.value = false; }
}
async function importNovel() {
  if (!importText.value.trim()) return emit('error', '请先粘贴小说原文');
  busy.value = true;
  try { await api.importNovel(props.projectId, importName.value, importText.value); importText.value = ''; importOpen.value = false; emit('refresh'); }
  catch (e) { emit('error', e.message); }
  finally { busy.value = false; }
}
async function upload(event) {
  const file = event.target.files[0]; if (!file) return;
  busy.value = true;
  try { await api.uploadNovel(props.projectId, file); importOpen.value = false; emit('refresh'); }
  catch (e) { emit('error', e.message); }
  finally { busy.value = false; event.target.value = ''; }
}
async function add() {
  if (!novel.value) novel.value = { name: importName.value, text: '', chapters: [], character_count: 0 };
  const chapter = { id: newId(), title: `第 ${chapters.value.length + 1} 章`, content: '', paragraphs: [] };
  chapters.value.splice(selectedIndex.value + 1 || chapters.value.length, 0, chapter); selectedId.value = chapter.id; await save(true);
}
async function remove(index) {
  if (!window.confirm(`删除「${chapters.value[index].title}」？此操作会保存一个新版本。`)) return;
  const next = chapters.value[index + 1] || chapters.value[index - 1]; chapters.value.splice(index, 1); selectedId.value = next?.id || ''; await save(true);
}
async function move(index, direction) { const target = index + direction; if (target < 0 || target >= chapters.value.length) return; [chapters.value[index], chapters.value[target]] = [chapters.value[target], chapters.value[index]]; await save(true); }
async function split() {
  if (!selected.value) return;
  const position = editor.value?.selectionStart ?? selected.value.content.length;
  const before = selected.value.content.slice(0, position).trim(); const after = selected.value.content.slice(position).trim();
  if (!before || !after) return emit('error', '请把光标放在正文中需要拆分的位置');
  selected.value.content = before;
  chapters.value.splice(selectedIndex.value + 1, 0, { id: newId(), title: `${selected.value.title}（下）`, content: after, paragraphs: [] });
  selected.value.title += '（上）'; selectedId.value = chapters.value[selectedIndex.value + 1].id; await save(true);
}
async function merge(index) {
  if (index < 0 || index >= chapters.value.length - 1) return;
  const current = chapters.value[index]; const next = chapters.value[index + 1];
  current.content = `${current.content}\n\n${next.content}`.trim(); current.title = `${current.title} / ${next.title}`; chapters.value.splice(index + 1, 1); selectedId.value = current.id; await save(true);
}
async function choose(id) { selectedId.value = id; await nextTick(); }
defineExpose({ save });
</script>

<template>
  <div>
    <div class="chapter-toolbar"><div><strong>{{ novel?.name || '项目小说章节' }}</strong><span v-if="novel">{{ chapters.length }} 章 · {{ novel.character_count.toLocaleString() }} 字</span><span v-else>在剧集规划确认后，导入并整理原著。</span></div><div><button class="btn secondary small" @click="importOpen = !importOpen"><SvgIcon name="upload" :size="15" />{{ novel ? '重新导入' : '导入小说' }}</button><button class="btn secondary small" @click="add"><SvgIcon name="plus" :size="15" />新建章节</button><button v-if="novel" class="btn primary small" :disabled="saving" @click="save(true)">{{ saving ? '保存中…' : saved ? '已保存' : '保存章节' }}</button></div></div>

    <section v-if="importOpen || !novel" class="import-section">
      <div class="import-copy"><span class="import-icon"><SvgIcon name="book" :size="22" /></span><div><h3>{{ novel ? '导入新原文' : '把小说原文放入项目' }}</h3><p>支持 TXT、DOCX、EPUB。系统会识别“第 X 章／回／卷”，没有章节标题时按段落拆分。</p></div></div>
      <div class="import-name"><label>小说名称<input v-model="importName" placeholder="输入小说名称" /></label><label class="btn secondary file-button"><SvgIcon name="upload" :size="16" />选择文件<input type="file" accept=".txt,.docx,.epub" @change="upload" hidden /></label></div>
      <textarea v-model="importText" class="paste-input" placeholder="也可以直接粘贴完整小说原文…"></textarea>
      <div class="import-bottom"><span>{{ novel ? '重新导入会生成新内容版本，原版本仍保留。' : '导入后仍可逐章修改、拆分与合并。' }}</span><button class="btn primary" :disabled="busy || !importText.trim()" @click="importNovel">{{ busy ? '正在解析…' : '导入并解析章节' }}</button></div>
    </section>

    <div v-if="novel" class="chapters-workspace">
      <aside class="chapter-list"><div class="list-heading"><span>章节目录</span><b>{{ chapters.length }}</b></div><button v-for="(chapter, index) in chapters" :key="chapter.id" :class="{ active: selectedId === chapter.id }" @click="choose(chapter.id)"><span>{{ String(index + 1).padStart(2, '0') }}</span><div><strong>{{ chapter.title }}</strong><small>{{ (chapter.content || '').length }} 字</small></div></button><div v-if="!chapters.length" class="list-empty">还没有章节<br />请新建或导入小说。</div></aside>
      <section v-if="selected" class="chapter-editor"><div class="chapter-title-row"><span>第 {{ selectedIndex + 1 }} 章</span><input v-model="selected.title" @input="saved = false" placeholder="章节标题" /></div><textarea ref="editor" v-model="selected.content" class="chapter-content" placeholder="输入或粘贴本章正文…" @input="saved = false"></textarea><div class="chapter-meta"><span>{{ (selected.content || '').length }} 字 · 修改后记得保存</span><span>在正文中定位光标，可从该位置拆分为两章</span></div><div class="chapter-actions"><button :disabled="selectedIndex === 0" @click="move(selectedIndex, -1)">上移</button><button :disabled="selectedIndex === chapters.length - 1" @click="move(selectedIndex, 1)">下移</button><button @click="split">从光标处拆分</button><button :disabled="selectedIndex === chapters.length - 1" @click="merge(selectedIndex)">与下一章合并</button><button class="delete" @click="remove(selectedIndex)">删除本章</button><button class="btn primary small" @click="save(true)">保存本章</button></div></section>
      <section v-else class="chapter-editor empty-editor"><SvgIcon name="book" :size="28" /><h3>选择或新建一个章节</h3></section>
    </div>
  </div>
</template>

<style scoped>
.chapter-toolbar{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:15px}.chapter-toolbar strong{display:block;font-size:14px}.chapter-toolbar span{display:block;font-size:11px;color:var(--text-secondary);margin-top:4px}.chapter-toolbar>div:last-child{display:flex;gap:7px;flex-wrap:wrap}.import-section{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:22px;margin-bottom:16px}.import-copy{display:flex;align-items:flex-start;gap:12px}.import-icon{display:grid;place-items:center;width:42px;height:42px;background:var(--accent-soft);color:var(--accent);border-radius:10px;flex-shrink:0}.import-copy h3{margin:0 0 6px;font-size:16px}.import-copy p{margin:0;color:var(--text-secondary);font-size:12px;line-height:1.7}.import-name{display:flex;align-items:flex-end;gap:12px;margin:18px 0 12px}.import-name label:first-child{flex:1;font-size:12px}.import-name input{display:block;width:100%;margin-top:6px}.file-button{cursor:pointer}.paste-input{min-height:200px;line-height:1.8}.import-bottom{display:flex;align-items:center;justify-content:space-between;margin-top:12px;gap:12px}.import-bottom span{font-size:11px;color:var(--text-secondary)}.chapters-workspace{display:grid;grid-template-columns:260px minmax(0,1fr);min-height:610px;background:var(--surface);border:1px solid var(--border);border-radius:12px;overflow:hidden}.chapter-list{border-right:1px solid var(--border);max-height:720px;overflow:auto;background:#fafbfc}.list-heading{display:flex;justify-content:space-between;padding:16px;border-bottom:1px solid var(--border);font-size:12px;font-weight:650}.list-heading b{color:var(--text-tertiary)}.chapter-list>button{display:flex;align-items:flex-start;gap:10px;width:100%;padding:13px 14px;background:transparent;color:var(--text);text-align:left;border-bottom:1px solid var(--border-light);border-radius:0}.chapter-list>button>span{font-size:10px;color:var(--text-tertiary);padding-top:2px}.chapter-list>button strong{display:block;font-size:12px;font-weight:550;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:170px}.chapter-list>button small{display:block;font-size:10px;color:var(--text-tertiary);margin-top:5px}.chapter-list>button.active{background:var(--accent-soft);box-shadow:inset 3px 0 var(--accent)}.chapter-list>button.active>span{color:var(--accent)}.list-empty{text-align:center;padding:60px 10px;color:var(--text-tertiary);font-size:12px;line-height:1.8}.chapter-editor{padding:22px;display:flex;flex-direction:column;min-width:0}.chapter-title-row{display:flex;align-items:center;gap:13px}.chapter-title-row>span{font-size:10px;white-space:nowrap;color:var(--accent);font-weight:650}.chapter-title-row input{font-size:17px;font-weight:650;border:0;border-bottom:1px solid var(--border);background:transparent;border-radius:0;padding:8px 0;width:100%}.chapter-content{flex:1;min-height:440px;border:0;background:transparent;resize:none;padding:24px 0;font:14px/2 var(--font);outline:none}.chapter-meta{display:flex;justify-content:space-between;color:var(--text-tertiary);font-size:10px;border-top:1px solid var(--border);padding-top:12px}.chapter-actions{display:flex;align-items:center;gap:11px;margin-top:14px;flex-wrap:wrap}.chapter-actions>button:not(.btn){background:transparent;color:var(--text-secondary);font-size:11px;padding:5px 0}.chapter-actions .delete{color:#ad4840!important}.chapter-actions .btn{margin-left:auto}.empty-editor{align-items:center;justify-content:center;color:var(--text-tertiary)}@media(max-width:850px){.chapters-workspace{grid-template-columns:210px minmax(0,1fr)}.chapter-list>button strong{max-width:125px}.chapter-meta span:last-child{display:none}}@media(max-width:650px){.chapter-toolbar{align-items:flex-start;flex-direction:column}.import-name{align-items:stretch;flex-direction:column}.import-bottom{align-items:flex-start;flex-direction:column}.chapters-workspace{display:block}.chapter-list{display:flex;max-height:none;overflow:auto;border-right:0;border-bottom:1px solid var(--border)}.list-heading{display:none}.chapter-list>button{min-width:160px;border-bottom:0;border-right:1px solid var(--border-light)}.chapter-list>button.active{box-shadow:inset 0 -3px var(--accent)}.chapter-editor{padding:16px}.chapter-content{min-height:400px}.chapter-actions .btn{margin-left:0;width:100%}}
</style>
