<script setup>
import { ref, watch } from 'vue';
import { api } from '../../services/api';
import SvgIcon from '../SvgIcon.vue';
const props = defineProps({ projectId: String, state: Object });
const emit = defineEmits(['refresh', 'error', 'episodes']);
const plan = ref({ episodes: [] }); const busy = ref(false); const expanded = ref(0);
watch(() => props.state, s => { plan.value = JSON.parse(JSON.stringify(s?.content?.episodes ? s.content : { episodes: [] })); if (plan.value.episodes.length) emit('episodes', plan.value.episodes); }, { immediate: true, deep: false });
async function generate() { busy.value = true; try { await api.generateStage(props.projectId, 2); emit('refresh'); } catch(e) { emit('error', e.message); } finally { busy.value = false; } }
async function save() { if (!plan.value.episodes.length) return; try { const result = await api.saveStage(props.projectId, 2, plan.value); emit('episodes', plan.value.episodes); return result; } catch(e) { emit('error', e.message); throw e; } }
function add() { const number = plan.value.episodes.length + 1; plan.value.episodes.push({ episode_number: number, title: `第 ${number} 集`, source_chapters: [], main_plot: '', key_characters: [], main_conflict: '', opening_hook: '', dramatic_highlights: [], climax: '', cliffhanger: '', scene_requirements: [], estimated_duration: 90 }); expanded.value = plan.value.episodes.length - 1; }
function move(index, direction) { const target = index + direction; if (target < 0 || target >= plan.value.episodes.length) return; [plan.value.episodes[index], plan.value.episodes[target]] = [plan.value.episodes[target], plan.value.episodes[index]]; plan.value.episodes.forEach((e, i) => e.episode_number = i + 1); expanded.value = target; save(); }
function merge(index) { if (index >= plan.value.episodes.length - 1) return; const current = plan.value.episodes[index], next = plan.value.episodes[index + 1]; current.title += ` / ${next.title}`; current.main_plot = `${current.main_plot}\n${next.main_plot}`; current.source_chapters = [...(current.source_chapters || []), ...(next.source_chapters || [])]; current.dramatic_highlights = [...(current.dramatic_highlights || []), ...(next.dramatic_highlights || [])]; current.estimated_duration = Number(current.estimated_duration || 90) + Number(next.estimated_duration || 90); plan.value.episodes.splice(index + 1, 1); plan.value.episodes.forEach((e, i) => e.episode_number = i + 1); save(); }
function split(index) { const copy = JSON.parse(JSON.stringify(plan.value.episodes[index])); copy.title += '（下）'; plan.value.episodes[index].title += '（上）'; plan.value.episodes.splice(index + 1, 0, copy); plan.value.episodes.forEach((e, i) => e.episode_number = i + 1); save(); }
function list(value) { return Array.isArray(value) ? value.join('、') : value || ''; }
function setList(episode, key, value) { episode[key] = value.split(/[、,，\n]/).map(v => v.trim()).filter(Boolean); }
defineExpose({ save });
</script>
<template>
  <div>
    <div class="stage-actions"><div><strong>剧集总规划</strong><span>每一集都可以独立进入后续剧本制作。</span></div><div><button class="btn secondary small" @click="add"><SvgIcon name="plus" :size="15" />添加剧集</button><button class="btn primary small" :disabled="busy" @click="generate"><SvgIcon name="spark" :size="16" />{{ busy ? 'AI 正在规划…' : plan.episodes.length ? '重新生成规划' : '生成剧集规划' }}</button></div></div>
    <section v-if="!plan.episodes.length" class="empty-content"><SvgIcon name="queue" :size="30" /><h3>还没有剧集规划</h3><p>AI 会根据已审批的 Story Bible 和原著章节，规划每集冲突、高光和结尾。</p><button class="btn primary" :disabled="busy" @click="generate">开始规划</button></section>
    <div v-else class="episode-plan-list">
      <article v-for="(episode, index) in plan.episodes" :key="index" class="plan-card">
        <button class="plan-summary" @click="expanded = expanded === index ? -1 : index"><span class="episode-number">{{ String(episode.episode_number).padStart(2, '0') }}</span><span class="plan-title"><strong>{{ episode.title }}</strong><small>{{ list(episode.source_chapters) || '待设置原著章节' }}</small></span><span class="duration">{{ episode.estimated_duration }} 秒</span><span class="plan-status">待制作</span><SvgIcon name="chevron" :size="16" /></button>
        <div v-if="expanded === index" class="plan-editor">
          <div class="form-grid"><label>剧集标题<input v-model="episode.title" @blur="save" /></label><label>预计时长（秒）<input type="number" v-model.number="episode.estimated_duration" @blur="save" /></label></div>
          <label>原著章节映射<input :value="list(episode.source_chapters)" @change="setList(episode, 'source_chapters', $event.target.value); save()" placeholder="第一章、第二章" /></label>
          <label>本集主线<textarea v-model="episode.main_plot" @blur="save"></textarea></label>
          <div class="form-grid"><label>核心冲突<textarea v-model="episode.main_conflict" @blur="save"></textarea></label><label>开场钩子<textarea v-model="episode.opening_hook" @blur="save"></textarea></label></div>
          <label>关键角色<input :value="list(episode.key_characters)" @change="setList(episode, 'key_characters', $event.target.value); save()" /></label>
          <label>戏剧高光<textarea :value="list(episode.dramatic_highlights)" @change="setList(episode, 'dramatic_highlights', $event.target.value); save()"></textarea></label>
          <div class="form-grid"><label>高潮<textarea v-model="episode.climax" @blur="save"></textarea></label><label>结尾悬念<textarea v-model="episode.cliffhanger" @blur="save"></textarea></label></div>
          <div class="plan-edit-actions"><button class="text-btn" @click="move(index, -1)">上移</button><button class="text-btn" @click="move(index, 1)">下移</button><button class="text-btn" @click="split(index)">拆分</button><button class="text-btn" @click="merge(index)">与下一集合并</button><button class="btn primary small" @click="save">保存本集</button></div>
        </div>
      </article>
    </div>
  </div>
</template>
<style scoped>
.stage-actions{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.stage-actions>div{display:flex;gap:8px}.stage-actions>div:first-child{display:block}.stage-actions strong{display:block}.stage-actions span{font-size:12px;color:var(--text-secondary)}.empty-content{text-align:center;padding:100px 20px;background:var(--surface);border:1px dashed var(--border-strong);border-radius:12px;color:var(--text-secondary)}.empty-content h3{color:var(--text)}.episode-plan-list{display:flex;flex-direction:column;gap:10px}.plan-card{background:var(--surface);border:1px solid var(--border);border-radius:11px;overflow:hidden}.plan-summary{display:grid;grid-template-columns:48px 1fr auto auto 20px;align-items:center;gap:14px;width:100%;padding:16px;background:transparent;color:var(--text);text-align:left;border-radius:0}.episode-number{display:grid;place-items:center;width:40px;height:40px;background:var(--accent-soft);color:var(--accent);border-radius:9px;font-weight:700}.plan-title strong,.plan-title small{display:block}.plan-title small{color:var(--text-secondary);margin-top:4px}.duration,.plan-status{font-size:12px;color:var(--text-secondary)}.plan-status{padding:4px 8px;background:#f0f2f5;border-radius:99px}.plan-editor{padding:20px;border-top:1px solid var(--border);background:#fbfcfd}.plan-editor label{display:block;font-size:12px;font-weight:600;margin:12px 0}.plan-editor input,.plan-editor textarea{width:100%;margin-top:6px}.plan-editor textarea{min-height:75px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.plan-edit-actions{display:flex;align-items:center;gap:12px;margin-top:16px}.plan-edit-actions .btn{margin-left:auto}.text-btn{background:transparent;color:var(--text-secondary);padding:5px;font-size:12px}@media(max-width:650px){.stage-actions{align-items:flex-start;gap:12px}.stage-actions>div{flex-wrap:wrap}.plan-summary{grid-template-columns:42px 1fr 18px}.duration,.plan-status{display:none}.form-grid{grid-template-columns:1fr}}
</style>
