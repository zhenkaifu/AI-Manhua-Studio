<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { api } from '../services/api';
import SvgIcon from '../components/SvgIcon.vue';
import StoryBibleStage from '../components/stages/StoryBibleStage.vue';
import PlanningStage from '../components/stages/PlanningStage.vue';
import ChaptersStage from '../components/stages/ChaptersStage.vue';
import ScriptStage from '../components/stages/ScriptStage.vue';
import AssetsStage from '../components/stages/AssetsStage.vue';
import StoryboardStage from '../components/stages/StoryboardStage.vue';
import ImagesStage from '../components/stages/ImagesStage.vue';
import ReadyStage from '../components/stages/ReadyStage.vue';
import QueueView from './QueueView.vue';

const props = defineProps({ projectId: { type: String, required: true }, initialStage: { type: Number, default: 1 } });
const emit = defineEmits(['back', 'project-change']);
const STAGES = [
  { id: 1, name: '故事设定', short: 'Story Bible', icon: 'edit', description: '由你定义题材、主角、核心爽点与故事走向，AI 提供可编辑建议。' },
  { id: 2, name: '剧集规划', short: '拆分剧集', icon: 'queue', description: '依据已审批的故事设定，规划每集主线、冲突、高光与结尾。' },
  { id: 3, name: '小说章节', short: '原著管理', icon: 'book', description: '导入并管理项目小说，逐章编辑、排序、拆分与合并。' },
  { id: 4, name: '剧本制作', short: '小说改编', icon: 'edit', description: '尽可能保留原著情节、动机、伏笔和台词，改编为完整可表演的场景剧本。' },
  { id: 5, name: '资产管理', short: '统一视觉', icon: 'users', description: '管理角色、场景与重要道具，统一参考图和视觉设定。' },
  { id: 6, name: '分镜制作', short: '镜头语言', icon: 'grid', description: '把已审批剧本转为可编辑镜头，并关联已有视觉资产。' },
  { id: 7, name: '图像生成与审核', short: '生成定稿', icon: 'image', description: '生成候选图、比较版本，由你逐镜头选择最终画面。' },
  { id: 8, name: '视频制作就绪', short: '整理交付', icon: 'check', description: '检查交付完整性，导出供视频制作使用的 JSON 制作包。' },
];
const STATUS = { NOT_STARTED: '未开始', IN_PROGRESS: '制作中', AI_GENERATING: 'AI 生成中', REVIEW_REQUIRED: '待人工审批', APPROVED: '已审批', NEEDS_REVISION: '需要修订', FAILED: '生成失败' };
const workflow = ref(null); const project = ref(null); const episodes = ref([]); const currentStage = ref(1); const currentEpisodeId = ref(''); const stageData = ref(null); const loading = ref(true); const stageLoading = ref(false); const busy = ref(false); const error = ref(''); const notice = ref(''); const stageRef = ref(null); const queueOpen = ref(false); const activeCount = ref(0); const mobileSteps = ref(false);
let queueTimer = null;
const episodeScoped = computed(() => [4, 6, 7, 8].includes(currentStage.value));
const activeMeta = computed(() => STAGES[currentStage.value - 1]);
const activeState = computed(() => stageData.value?.episode_state || stageData.value);
const currentEpisode = computed(() => episodes.value.find(e => e.id === currentEpisodeId.value));
const stageStates = computed(() => workflow.value?.stages || []);
const unlockedThrough = computed(() => Math.max(1, ...stageStates.value.filter(s => s.unlocked).map(s => s.id || s.stage)));

function persist() {
  localStorage.setItem('manhua:last-project', JSON.stringify({ projectId: props.projectId, stage: currentStage.value, episodeId: currentEpisodeId.value }));
}
async function loadQueueCount() {
  try { const jobs = await api.listJobs(props.projectId); activeCount.value = jobs.filter(j => ['pending', 'running'].includes(j.status)).length; } catch {}
}
async function loadBase() {
  loading.value = true; error.value = '';
  try {
    [workflow.value, project.value, episodes.value] = await Promise.all([api.workflow(props.projectId), api.listProjects().then(rows => rows.find(p => p.id === props.projectId)), api.listEpisodes(props.projectId)]);
    currentEpisodeId.value = episodes.value.some(e => e.id === workflow.value.last_active_episode_id) ? workflow.value.last_active_episode_id : episodes.value[0]?.id || '';
    const requested = props.initialStage;
    currentStage.value = stageStates.value.find(s => s.stage === requested)?.unlocked ? requested : workflow.value.current_stage;
    if (!stageStates.value.find(s => s.stage === currentStage.value)?.unlocked) currentStage.value = 1;
    await openStage(currentStage.value, false);
  } catch (e) { error.value = e.message; }
  finally { loading.value = false; }
}
async function loadStage() {
  if (!currentStage.value) return;
  stageLoading.value = true; error.value = '';
  try {
    stageData.value = await api.stage(props.projectId, currentStage.value, episodeScoped.value ? currentEpisodeId.value : null);
    persist();
  } catch (e) { error.value = e.message; }
  finally { stageLoading.value = false; }
}
async function openStage(stage, record = true) {
  const target = stageStates.value.find(s => s.stage === stage);
  if (!target?.unlocked) { error.value = `请先审批「${STAGES[stage - 2]?.name}」`; return; }
  currentStage.value = stage; notice.value = ''; error.value = ''; mobileSteps.value = false;
  try { if (record) workflow.value = await api.resumeProject(props.projectId, stage, currentEpisodeId.value || null); } catch (e) { error.value = e.message; }
  await loadStage();
}
async function selectEpisode(id) {
  currentEpisodeId.value = id; error.value = ''; notice.value = '';
  try { workflow.value = await api.resumeProject(props.projectId, currentStage.value, id); } catch (e) { error.value = e.message; }
  await loadStage();
}
async function refresh() {
  try {
    const [freshWorkflow, freshEpisodes] = await Promise.all([api.workflow(props.projectId), api.listEpisodes(props.projectId)]);
    workflow.value = freshWorkflow; episodes.value = freshEpisodes;
    if (!currentEpisodeId.value && freshEpisodes.length) currentEpisodeId.value = freshEpisodes[0].id;
    await loadStage(); await loadQueueCount(); emit('project-change');
  } catch (e) { error.value = e.message; }
}
async function approve() {
  busy.value = true; error.value = ''; notice.value = '';
  try {
    if (stageRef.value?.save) await stageRef.value.save();
    await api.approveStage(props.projectId, currentStage.value, episodeScoped.value ? currentEpisodeId.value : null);
    const approvedName = activeMeta.value.name;
    await refresh();
    notice.value = `「${approvedName}」已通过人工审批。`;
    if (currentStage.value < 8) await openStage(currentStage.value + 1);
  } catch (e) { error.value = e.message; }
  finally { busy.value = false; }
}
async function reject() {
  if (!window.confirm('将本阶段退回为“需要修订”？已保存的内容和版本不会丢失。')) return;
  busy.value = true; error.value = '';
  try { await api.rejectStage(props.projectId, currentStage.value, episodeScoped.value ? currentEpisodeId.value : null); await refresh(); notice.value = '已退回修改，完善后可再次提交审批。'; }
  catch (e) { error.value = e.message; }
  finally { busy.value = false; }
}
function onPlannedEpisodes(items) {
  if (!items?.length) return;
  items.forEach(item => { const existing = episodes.value.find(e => e.id === item.id); if (existing) Object.assign(existing, item); else episodes.value.push(item); });
  if (!currentEpisodeId.value) currentEpisodeId.value = items[0].id;
}
onMounted(() => { loadBase(); loadQueueCount(); queueTimer = setInterval(loadQueueCount, 2500); });
onBeforeUnmount(() => clearInterval(queueTimer));
</script>

<template>
  <div class="workspace-shell">
    <header class="workspace-topbar">
      <div class="workspace-project"><button class="icon-btn back-button" title="返回项目" @click="emit('back')"><SvgIcon name="back" :size="19" /></button><div><span>项目工作台</span><h1>{{ project?.name || '正在读取项目' }}</h1></div></div>
      <div class="topbar-right"><span v-if="currentEpisode && episodeScoped" class="episode-context">第 {{ currentEpisode.episode_number }} 集</span><button class="queue-button" @click="queueOpen = true"><SvgIcon name="queue" :size="17" /><span>生成队列</span><b v-if="activeCount">{{ activeCount }}</b></button></div>
    </header>

    <div class="mobile-stage-select"><button @click="mobileSteps = !mobileSteps"><span>{{ String(currentStage).padStart(2, '0') }} · {{ activeMeta.name }}</span><SvgIcon name="chevron" :size="16" /></button></div>
    <div class="workspace-body">
      <aside class="stage-sidebar" :class="{ open: mobileSteps }">
        <div class="sidebar-caption">制作流程 <span>8 STAGES</span></div>
        <nav>
          <button v-for="stage in STAGES" :key="stage.id" class="stage-nav-item" :class="{ active: currentStage === stage.id, locked: !stageStates[stage.id - 1]?.unlocked }" @click="openStage(stage.id)">
            <span class="stage-number"><SvgIcon v-if="stageStates[stage.id - 1]?.status === 'APPROVED'" name="check" :size="15" /><SvgIcon v-else-if="!stageStates[stage.id - 1]?.unlocked" name="lock" :size="14" /><template v-else>{{ String(stage.id).padStart(2, '0') }}</template></span>
            <span class="stage-label"><strong>{{ stage.name }}</strong><small>{{ stage.short }}</small></span>
            <i v-if="stageStates[stage.id - 1]?.status === 'NEEDS_REVISION'" title="需要修订"></i>
          </button>
        </nav>
        <div class="workflow-note"><SvgIcon name="lock" :size="15" /><p>逐阶段人工审批<br />修改上游会提醒复核下游</p></div>
      </aside>

      <main class="workspace-main">
        <div v-if="loading" class="workspace-loading">正在恢复上次的制作位置…</div>
        <template v-else>
          <header class="stage-heading"><div><p>STAGE {{ String(currentStage).padStart(2, '0') }} / 08</p><h2>{{ activeMeta.name }}</h2><span>{{ activeMeta.description }}</span></div><div class="stage-state"><span v-if="activeState" class="status-chip" :class="activeState.status?.toLowerCase()">{{ STATUS[activeState.status] || activeState.status }}</span><small v-if="activeState?.version">内容版本 v{{ activeState.version }}</small></div></header>
          <div v-if="error" class="workspace-alert error-alert"><span>{{ error }}</span><button @click="error = ''">×</button></div>
          <div v-if="notice" class="workspace-alert notice-alert"><SvgIcon name="check" :size="17" /><span>{{ notice }}</span><button @click="notice = ''">×</button></div>
          <div v-if="activeState?.outdated" class="workspace-alert warning-alert">上游内容有更新，请复核本阶段后再审批。</div>

          <div class="stage-content" :class="{ refreshing: stageLoading }">
            <StoryBibleStage v-if="currentStage === 1" ref="stageRef" :project-id="projectId" :state="stageData" @refresh="refresh" @error="error = $event" />
            <PlanningStage v-else-if="currentStage === 2" ref="stageRef" :project-id="projectId" :state="stageData" @refresh="refresh" @error="error = $event" @episodes="onPlannedEpisodes" />
            <ChaptersStage v-else-if="currentStage === 3" ref="stageRef" :project-id="projectId" :state="stageData" @refresh="refresh" @error="error = $event" />
            <ScriptStage v-else-if="currentStage === 4" ref="stageRef" :project-id="projectId" :state="stageData" :episode-id="currentEpisodeId" :episodes="episodes" @refresh="refresh" @error="error = $event" @select-episode="selectEpisode" />
            <AssetsStage v-else-if="currentStage === 5" ref="stageRef" :project-id="projectId" :state="stageData" @refresh="refresh" @error="error = $event" />
            <StoryboardStage v-else-if="currentStage === 6" ref="stageRef" :project-id="projectId" :state="stageData" :episode-id="currentEpisodeId" :episodes="episodes" @refresh="refresh" @error="error = $event" @select-episode="selectEpisode" />
            <ImagesStage v-else-if="currentStage === 7" ref="stageRef" :project-id="projectId" :episode-id="currentEpisodeId" @select-episode="selectEpisode" />
            <ReadyStage v-else-if="currentStage === 8" ref="stageRef" :project-id="projectId" :episode-id="currentEpisodeId" :episodes="episodes" @refresh="refresh" @error="error = $event" @select-episode="selectEpisode" />
          </div>

          <footer class="stage-footer"><button class="btn secondary" :disabled="currentStage === 1 || busy" @click="openStage(currentStage - 1)"><SvgIcon name="back" :size="16" />上一步</button><div class="approval-actions"><button v-if="activeState?.content && Object.keys(activeState.content).length" class="text-action" :disabled="busy" @click="reject">退回修改</button><button class="btn primary approve-button" :disabled="busy || !activeState || activeState.status === 'NOT_STARTED'" @click="approve"><SvgIcon name="check" :size="17" />{{ busy ? '正在提交…' : activeState?.status === 'APPROVED' ? '重新审批并继续' : currentStage === 8 ? '审批并完成制作准备' : '审批并进入下一阶段' }}</button></div><button class="btn secondary next-button" :disabled="currentStage === 8 || busy || !stageStates[currentStage]?.unlocked" @click="openStage(currentStage + 1)">下一步<SvgIcon name="arrow" :size="16" /></button></footer>
        </template>
      </main>
    </div>

    <div v-if="queueOpen" class="queue-drawer-mask" @click.self="queueOpen = false"><aside class="queue-drawer"><div class="drawer-heading"><span>项目实时任务</span><button class="icon-btn" @click="queueOpen = false">×</button></div><QueueView :project-id="projectId" @active-change="activeCount = $event" /></aside></div>
  </div>
</template>

<style scoped>
.workspace-shell{min-height:100vh;background:var(--page)}.workspace-topbar{height:68px;background:var(--surface);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;padding:0 26px;position:sticky;top:0;z-index:8}.workspace-project{display:flex;align-items:center;gap:12px}.back-button{border:1px solid var(--border);background:var(--surface)}.workspace-project span{display:block;font-size:10px;color:var(--text-tertiary);margin-bottom:2px}.workspace-project h1{font-size:15px;margin:0}.topbar-right{display:flex;align-items:center;gap:18px}.episode-context{font-size:12px;color:var(--text-secondary)}.queue-button{display:flex;align-items:center;gap:7px;background:var(--surface);border:1px solid var(--border);color:var(--text);padding:8px 12px;font-size:12px}.queue-button b{display:grid;place-items:center;background:var(--accent);color:white;border-radius:99px;min-width:18px;height:18px;font-size:10px}.workspace-body{display:grid;grid-template-columns:218px minmax(0,1fr);min-height:calc(100vh - 68px)}.stage-sidebar{position:sticky;top:68px;height:calc(100vh - 68px);background:#fbfbfc;border-right:1px solid var(--border);padding:24px 14px;display:flex;flex-direction:column}.sidebar-caption{font-size:11px;color:var(--text-secondary);padding:0 10px 15px;display:flex;justify-content:space-between}.sidebar-caption span{font-size:9px;letter-spacing:1.3px;color:var(--text-tertiary)}.stage-sidebar nav{display:flex;flex-direction:column;gap:4px}.stage-nav-item{position:relative;display:flex;align-items:center;gap:11px;width:100%;padding:11px 10px;background:transparent;color:var(--text-secondary);text-align:left;border-radius:9px}.stage-nav-item:hover:not(.locked){background:#f0f1f5}.stage-nav-item.active{background:var(--accent-soft);color:var(--accent)}.stage-nav-item.locked{opacity:.48;cursor:not-allowed}.stage-number{display:grid;place-items:center;width:28px;height:28px;flex-shrink:0;font-size:10px;font-weight:650;border:1px solid var(--border);border-radius:8px;background:var(--surface)}.active .stage-number{border-color:#ccd2fa}.stage-label strong,.stage-label small{display:block}.stage-label strong{font-size:12px;font-weight:600}.stage-label small{font-size:10px;color:var(--text-tertiary);margin-top:3px}.active .stage-label small{color:#737dc1}.stage-nav-item>i{width:6px;height:6px;background:#d88a27;border-radius:50%;margin-left:auto}.workflow-note{margin-top:auto;border-top:1px solid var(--border);padding:18px 9px 0;display:flex;align-items:flex-start;gap:8px;color:var(--text-tertiary)}.workflow-note p{font-size:10px;line-height:1.7;margin:0}.workspace-main{min-width:0;padding:30px clamp(20px,3vw,42px) 0;max-width:1500px;width:100%;margin:0 auto}.stage-heading{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:24px}.stage-heading p{font-size:10px;letter-spacing:1.5px;color:var(--accent);font-weight:700;margin:0 0 7px}.stage-heading h2{font-size:27px;margin:0 0 7px;letter-spacing:-.4px}.stage-heading>div>span{font-size:13px;color:var(--text-secondary)}.stage-state{text-align:right}.status-chip{display:inline-block;padding:5px 10px;background:#eef0f4;color:#667085;border-radius:99px;font-size:11px}.status-chip.approved{background:#e9f6ee;color:#21734d}.status-chip.review_required{background:#eeefff;color:#575fb0}.status-chip.needs_revision,.status-chip.failed{background:#fff0e7;color:#a75c22}.status-chip.ai_generating{background:#edf0ff;color:#5363bb}.stage-state small{display:block;color:var(--text-tertiary);font-size:10px;margin-top:7px}.workspace-alert{display:flex;align-items:center;gap:8px;padding:11px 14px;border-radius:9px;margin-bottom:14px;font-size:12px}.workspace-alert button{margin-left:auto;background:transparent;color:inherit;padding:0 3px}.error-alert{background:#fff0ef;color:#a23b35;border:1px solid #f0d0cc}.notice-alert{background:#edf8f2;color:#236a47;border:1px solid #cde6d9}.warning-alert{background:#fff7e9;color:#8b5b18;border:1px solid #eddfc3}.stage-content{transition:opacity .15s;min-height:360px}.stage-content.refreshing{opacity:.55;pointer-events:none}.stage-footer{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:16px;border-top:1px solid var(--border);padding:20px 0 26px;margin-top:26px}.stage-footer>.btn{display:flex;align-items:center;gap:7px;justify-self:start}.approval-actions{display:flex;align-items:center;gap:14px}.text-action{background:transparent;color:var(--text-secondary);padding:8px;font-size:12px}.approve-button{display:flex;align-items:center;gap:7px}.stage-footer .next-button{justify-self:end}.workspace-loading{padding:140px 0;text-align:center;color:var(--text-secondary)}.queue-drawer-mask{position:fixed;inset:0;background:rgba(28,32,42,.28);z-index:30;display:flex;justify-content:flex-end}.queue-drawer{width:min(620px,100%);height:100%;overflow:auto;background:var(--page);padding:0 24px 30px;box-shadow:-10px 0 35px rgba(30,38,55,.12)}.drawer-heading{height:65px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);margin-bottom:24px;font-size:13px;font-weight:600}.mobile-stage-select{display:none}@media(max-width:950px){.workspace-body{grid-template-columns:180px minmax(0,1fr)}.stage-sidebar{padding:20px 9px}.stage-label small{display:none}.workspace-main{padding:24px 20px 0}.stage-footer{grid-template-columns:auto 1fr}.approval-actions{justify-self:end}.next-button{display:none!important}}@media(max-width:700px){.workspace-topbar{height:60px;padding:0 14px}.workspace-body{display:block}.stage-sidebar{display:none}.mobile-stage-select{display:block;padding:10px 14px;background:var(--surface);border-bottom:1px solid var(--border)}.mobile-stage-select>button{width:100%;display:flex;justify-content:space-between;background:transparent;color:var(--text);padding:7px}.stage-sidebar.open{display:flex;position:relative;top:0;height:auto;border-bottom:1px solid var(--border)}.stage-sidebar.open nav{display:grid;grid-template-columns:1fr 1fr;width:100%}.workflow-note{display:none}.workspace-main{padding:20px 14px 0}.stage-heading h2{font-size:23px}.stage-heading{gap:12px}.stage-heading>div>span{font-size:12px}.stage-footer{display:flex;justify-content:space-between;gap:8px}.stage-footer>.btn{font-size:0;padding:11px}.approval-actions{gap:5px}.approve-button{font-size:11px;padding:10px 12px}.text-action{display:none}.queue-button span{display:none}.episode-context{display:none}}
</style>

<style scoped>
.queue-drawer :deep(.queue-tabs){border-color:var(--border)}
.queue-drawer :deep(.queue-tabs button){color:var(--text-secondary)}
.queue-drawer :deep(.queue-tabs button.selected){color:var(--accent);background:var(--accent-soft);border-bottom-color:var(--accent)}
.queue-drawer :deep(.queue-tabs button span){color:var(--accent)}
.queue-drawer :deep(.job-card){background:var(--surface);border-color:var(--border)}
.queue-drawer :deep(.job-type){color:var(--accent);background:var(--accent-soft)}
.queue-drawer :deep(.job-status){color:var(--text-secondary)}
.queue-drawer :deep(.job-status.completed){color:#27845a}
.queue-drawer :deep(.job-status.failed){color:#b3443e}
.queue-drawer :deep(.live-summary){color:var(--accent);background:var(--accent-soft);border-color:#dfe3fa}
.queue-drawer :deep(.progress-meta){color:var(--text-secondary)}
.queue-drawer :deep(.progress-meta strong){color:var(--accent)}
.queue-drawer :deep(.progress-track){background:#e7eaf0}
.queue-drawer :deep(.progress-fill){background:var(--accent)}
.queue-drawer :deep(.empty-queue){border-color:var(--border-strong)}
.queue-drawer :deep(.empty-icon){color:#27845a}
</style>
