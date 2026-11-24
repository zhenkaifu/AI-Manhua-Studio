<script setup>
import { computed, onMounted, ref } from 'vue';
import { api } from '../services/api';
import SvgIcon from '../components/SvgIcon.vue';

const emit = defineEmits(['open']);
const projects = ref([]);
const loading = ref(true);
const error = ref('');
const query = ref('');
const filter = ref('all');
const showCreate = ref(false);
const creating = ref(false);
const form = ref({ name: '', description: '', visual_style: 'Chinese 2.5D Donghua' });
const filtered = computed(() => projects.value.filter(p => {
  const match = !query.value || `${p.name}${p.novel_name || ''}`.toLowerCase().includes(query.value.toLowerCase());
  return match && (filter.value === 'all' || (filter.value === 'done' ? p.progress === 100 : p.progress < 100));
}));

async function load() {
  try { projects.value = await api.dashboard(); error.value = ''; }
  catch (e) { error.value = e.message; }
  finally { loading.value = false; }
}
async function create() {
  if (!form.value.name.trim()) return;
  creating.value = true;
  try {
    const project = await api.createProject({ ...form.value, name: form.value.name.trim() });
    showCreate.value = false;
    form.value = { name: '', description: '', visual_style: 'Chinese 2.5D Donghua' };
    emit('open', project.id, 1);
  } catch (e) { error.value = e.message; }
  finally { creating.value = false; }
}
async function rename(project) {
  const name = window.prompt('项目名称', project.name);
  if (!name?.trim() || name === project.name) return;
  await api.updateProject(project.id, { name: name.trim() });
  load();
}
async function remove(project) {
  if (!window.confirm(`确定删除「${project.name}」？此操作会删除该项目的制作记录，且无法撤销。`)) return;
  try { await api.deleteProject(project.id); load(); }
  catch (e) { error.value = e.message; }
}
function fmt(value) {
  if (!value) return '尚未开始';
  return new Date(value).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}
onMounted(load);
</script>

<template>
  <div class="dashboard page-container">
    <header class="dashboard-hero">
      <div><p class="overline">PRODUCTION OVERVIEW</p><h1>你的漫剧项目</h1><p>从小说到可用于视频制作的标准化分镜与视觉资产。</p></div>
      <button class="btn primary create-btn" @click="showCreate = true"><SvgIcon name="plus" />新建项目</button>
    </header>

    <div class="project-stats">
      <div><span>全部项目</span><strong>{{ projects.length }}</strong></div>
      <div><span>制作中</span><strong>{{ projects.filter(p => p.progress < 100).length }}</strong></div>
      <div><span>已完成制作准备</span><strong>{{ projects.filter(p => p.progress === 100).length }}</strong></div>
    </div>

    <div class="toolbar">
      <label class="search-field"><SvgIcon name="search" :size="18" /><input v-model="query" placeholder="搜索项目或小说名称" /></label>
      <select v-model="filter" aria-label="筛选项目"><option value="all">全部状态</option><option value="active">制作中</option><option value="done">已完成</option></select>
    </div>
    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="loading" class="loading-state">正在读取项目…</div>
    <section v-else-if="filtered.length" class="project-grid">
      <article v-for="project in filtered" :key="project.id" class="project-card">
        <button class="cover" @click="emit('open', project.id, project.current_stage)">
          <img v-if="project.cover_asset_id" :src="api.assetFileUrl(project.cover_asset_id)" :alt="project.name" />
          <div v-else class="cover-placeholder"><SvgIcon name="book" :size="34" /><span>{{ project.name.slice(0, 2) }}</span></div>
          <span class="status-pill" :class="{ done: project.progress === 100 }">{{ project.status }}</span>
        </button>
        <div class="project-body">
          <div class="project-title"><div><h2>{{ project.name }}</h2><p>{{ project.novel_name || '尚未导入小说' }}</p></div><div class="row-actions"><button class="icon-btn" title="重命名" @click="rename(project)"><SvgIcon name="edit" :size="17" /></button><button class="icon-btn danger-icon" title="删除项目" @click="remove(project)"><SvgIcon name="trash" :size="17" /></button></div></div>
          <div class="project-counts"><span><strong>{{ project.episode_count }}</strong> 剧集</span><span><strong>{{ project.character_count }}</strong> 角色</span><span><strong>{{ project.scene_count }}</strong> 场景</span></div>
          <div class="project-progress"><div><span>制作进度</span><strong>{{ project.progress }}%</strong></div><div class="track"><i :style="{ width: `${project.progress}%` }"></i></div></div>
          <div class="current-stage"><span>当前阶段</span><strong>{{ String(project.current_stage).padStart(2, '0') }} · {{ project.current_stage_name }}</strong></div>
          <div class="project-footer"><span><SvgIcon name="clock" :size="14" />{{ fmt(project.updated_at) }}</span><button class="continue-btn" @click="emit('open', project.id, project.current_stage)">继续制作<SvgIcon name="arrow" :size="16" /></button></div>
        </div>
      </article>
    </section>
    <section v-else class="empty-projects"><div class="empty-symbol"><SvgIcon name="folder" :size="32" /></div><h2>{{ query ? '没有匹配的项目' : '开始你的第一部 AI 漫剧' }}</h2><p>{{ query ? '试试其他关键词或筛选条件。' : '导入小说，AI 会协助你完成分析、剧本、分镜与视觉资产。' }}</p><button v-if="!query" class="btn primary" @click="showCreate = true"><SvgIcon name="plus" />新建项目</button></section>

    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <form class="modal clean-modal" @submit.prevent="create" @keydown.esc="showCreate = false">
        <div class="modal-heading"><div><p class="overline">NEW PRODUCTION</p><h2>创建漫剧项目</h2></div><button type="button" class="icon-btn" @click="showCreate = false">×</button></div>
        <label>项目名称<input v-model="form.name" autofocus required placeholder="例如：修仙传 · 第一季" /></label>
        <label>项目简介<textarea v-model="form.description" placeholder="简要记录故事题材和制作目标（选填）"></textarea></label>
        <label>视觉风格<select v-model="form.visual_style"><option value="Chinese 2.5D Donghua">2.5D 国漫</option><option value="Chinese 2D Anime">2D 国漫</option><option value="Cinematic Fantasy Animation">电影感幻想动画</option><option value="Modern Manhua Flat Color">现代平涂漫画</option><option value="Chinese Ink Wash">东方水墨</option></select></label>
        <p class="form-note">创建后可在第一阶段粘贴小说或上传 TXT、DOCX、EPUB 文件。</p>
        <div class="modal-actions"><button type="button" class="btn secondary" @click="showCreate = false">取消</button><button class="btn primary" :disabled="creating || !form.name.trim()">{{ creating ? '创建中…' : '创建并开始' }}</button></div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.dashboard-hero{display:flex;justify-content:space-between;align-items:center;gap:24px;margin:18px 0 28px}.dashboard-hero h1{font-size:32px;letter-spacing:-.5px;margin:6px 0 8px}.dashboard-hero p:not(.overline){margin:0;color:var(--text-secondary)}.overline{font-size:11px;letter-spacing:1.8px;color:var(--accent);font-weight:700;margin:0}.create-btn{align-self:center}.project-stats{display:flex;gap:40px;padding:18px 24px;background:var(--surface);border:1px solid var(--border);border-radius:12px;margin-bottom:24px}.project-stats div{display:flex;align-items:baseline;gap:10px}.project-stats span{font-size:13px;color:var(--text-secondary)}.project-stats strong{font-size:23px}.toolbar{display:flex;justify-content:space-between;gap:16px;margin-bottom:20px}.search-field{display:flex;align-items:center;gap:9px;background:var(--surface);border:1px solid var(--border);border-radius:9px;padding:0 12px;width:340px;color:var(--text-tertiary)}.search-field input{border:0;background:transparent;outline:0;width:100%;height:40px}.toolbar select{min-width:130px}.project-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}.project-card{background:var(--surface);border:1px solid var(--border);border-radius:13px;overflow:hidden;transition:transform .18s,box-shadow .18s}.project-card:hover{transform:translateY(-2px);box-shadow:var(--shadow)}.cover{position:relative;display:block;width:100%;height:170px;padding:0;border:0;border-radius:0;background:#e9edf3;overflow:hidden}.cover img{width:100%;height:100%;object-fit:cover}.cover-placeholder{height:100%;display:flex;align-items:center;justify-content:center;gap:16px;color:#8a96a8;background:#e8edf2}.cover-placeholder span{font-size:30px;font-weight:700;color:#748196}.status-pill{position:absolute;top:12px;left:12px;background:rgba(255,255,255,.92);color:#4b5565;border-radius:999px;padding:5px 10px;font-size:11px}.status-pill.done{color:#167552}.project-body{padding:18px}.project-title{display:flex;justify-content:space-between;gap:8px}.project-title h2{font-size:18px;margin:0 0 5px}.project-title p{font-size:12px;color:var(--text-secondary);margin:0}.row-actions{display:flex;opacity:0;transition:opacity .15s}.project-card:hover .row-actions{opacity:1}.project-counts{display:flex;gap:20px;margin:18px 0;color:var(--text-secondary);font-size:12px}.project-counts strong{color:var(--text);font-size:14px;margin-right:3px}.project-progress>div:first-child{display:flex;justify-content:space-between;font-size:12px;color:var(--text-secondary)}.project-progress strong{color:var(--accent)}.track{height:5px;background:#e7eaf0;border-radius:9px;margin-top:8px;overflow:hidden}.track i{display:block;height:100%;background:var(--accent);border-radius:9px}.current-stage{display:flex;justify-content:space-between;font-size:12px;margin:16px 0;color:var(--text-secondary)}.current-stage strong{color:var(--text);font-weight:600}.project-footer{display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--border);padding-top:14px}.project-footer>span{display:flex;align-items:center;gap:5px;color:var(--text-tertiary);font-size:11px}.continue-btn{display:flex;align-items:center;gap:5px;background:transparent;color:var(--accent);padding:5px 0;font-size:13px;font-weight:600}.empty-projects{text-align:center;padding:80px 20px;border:1px dashed var(--border-strong);border-radius:14px;background:rgba(255,255,255,.5)}.empty-symbol{width:64px;height:64px;display:grid;place-items:center;margin:auto;background:#e9edfb;color:var(--accent);border-radius:16px}.empty-projects h2{margin:18px 0 8px}.empty-projects p{color:var(--text-secondary);margin:0 0 22px}.clean-modal label{display:block;text-align:left;font-size:13px;font-weight:600;margin:16px 0 6px}.clean-modal input,.clean-modal textarea,.clean-modal select{width:100%;margin-top:7px}.clean-modal textarea{min-height:90px}.modal-heading{display:flex;justify-content:space-between;align-items:flex-start}.modal-heading h2{margin:5px 0}.form-note{font-size:12px;color:var(--text-secondary);line-height:1.6}.modal-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:22px}@media(max-width:1100px){.project-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.dashboard-hero{align-items:flex-start}.dashboard-hero h1{font-size:27px}.create-btn{font-size:0;padding:11px}.create-btn svg{margin:0}.project-stats{gap:18px;justify-content:space-between;padding:15px}.project-stats div{display:block}.project-stats span{font-size:11px}.project-grid{grid-template-columns:1fr}.toolbar{flex-wrap:wrap}.search-field{width:100%}.row-actions{opacity:1}}
</style>
