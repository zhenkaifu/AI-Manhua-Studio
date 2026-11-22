<script setup>
import { onMounted, ref } from 'vue';
import { api } from './services/api';
import SvgIcon from './components/SvgIcon.vue';
import DashboardView from './views/DashboardView.vue';
import WorkspaceView from './views/WorkspaceView.vue';
import AssetLibraryView from './views/AssetLibraryView.vue';
import SettingsView from './views/SettingsView.vue';

const view = ref('dashboard'); const projects = ref([]); const currentProjectId = ref(''); const initialStage = ref(1); const dashboardKey = ref(0); const error = ref('');
const NAV = [{ key: 'dashboard', label: '仪表盘', icon: 'grid' }, { key: 'projects', label: '项目', icon: 'folder' }, { key: 'assets', label: '资产库', icon: 'library' }, { key: 'settings', label: '设置', icon: 'settings' }];
async function loadProjects() { try { projects.value = await api.listProjects(); error.value = ''; } catch (e) { error.value = e.message; } }
function openWorkspace(id, stage = 1) { currentProjectId.value = id; initialStage.value = Number(stage) || 1; view.value = 'workspace'; }
function navigate(key) {
  error.value = '';
  if (key === 'projects') {
    let recent = null;
    try { recent = JSON.parse(localStorage.getItem('manhua:last-project') || 'null'); } catch {}
    const id = projects.value.some(p => p.id === recent?.projectId) ? recent.projectId : projects.value[0]?.id;
    if (id) openWorkspace(id, id === recent?.projectId ? recent.stage : 1);
    else view.value = 'dashboard';
  } else view.value = key;
}
function backToDashboard() { view.value = 'dashboard'; dashboardKey.value++; loadProjects(); }
onMounted(loadProjects);
</script>

<template>
  <WorkspaceView v-if="view === 'workspace'" :key="currentProjectId" :project-id="currentProjectId" :initial-stage="initialStage" @back="backToDashboard" @project-change="loadProjects" />
  <div v-else class="app-shell">
    <header class="app-header">
      <button class="brand" @click="view = 'dashboard'"><span class="brand-mark"><i></i><i></i><i></i></span><span><strong>AI Manhua Studio</strong><small>AI 漫剧创作工作台</small></span></button>
      <nav class="main-nav" aria-label="主导航"><button v-for="item in NAV" :key="item.key" :class="{ active: view === item.key }" @click="navigate(item.key)"><SvgIcon :name="item.icon" :size="17" /><span>{{ item.label }}</span></button></nav>
      <div class="local-badge"><i></i>本地工作区</div>
    </header>
    <main class="app-content"><p v-if="error" class="app-error">{{ error }}。请确认后端服务已启动。</p><DashboardView v-if="view === 'dashboard'" :key="dashboardKey" @open="openWorkspace" /><AssetLibraryView v-else-if="view === 'assets'" :projects="projects" :initial-project-id="currentProjectId" /><SettingsView v-else-if="view === 'settings'" /></main>
    <footer class="app-footer"><span>从小说到分镜制作包</span><span>本地创作 · 人工把关</span></footer>
  </div>
</template>

<style scoped>
.app-shell{min-height:100vh;display:flex;flex-direction:column}.app-header{height:70px;display:flex;align-items:center;gap:40px;padding:0 clamp(20px,4vw,56px);background:rgba(255,255,255,.94);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:10;backdrop-filter:blur(12px)}.brand{display:flex;align-items:center;gap:11px;background:transparent;color:var(--text);padding:0;text-align:left;flex-shrink:0}.brand-mark{width:34px;height:34px;display:flex;align-items:flex-end;justify-content:center;gap:3px;padding:8px;background:var(--accent);border-radius:10px;transform:rotate(-2deg)}.brand-mark i{display:block;width:4px;background:white;border-radius:3px}.brand-mark i:nth-child(1){height:11px}.brand-mark i:nth-child(2){height:18px}.brand-mark i:nth-child(3){height:14px}.brand strong,.brand small{display:block}.brand strong{font-size:15px;letter-spacing:-.2px}.brand small{font-size:9px;color:var(--text-tertiary);margin-top:2px;letter-spacing:.8px}.main-nav{display:flex;height:100%;gap:5px}.main-nav button{position:relative;display:flex;align-items:center;gap:7px;background:transparent;color:var(--text-secondary);padding:0 15px;border-radius:0;font-size:13px}.main-nav button:after{content:'';position:absolute;bottom:0;left:14px;right:14px;height:2px;background:transparent}.main-nav button.active{color:var(--accent);font-weight:600}.main-nav button.active:after{background:var(--accent)}.main-nav button:hover{color:var(--text)}.local-badge{margin-left:auto;display:flex;align-items:center;gap:6px;font-size:11px;color:var(--text-secondary);background:#f2f4f7;padding:6px 10px;border-radius:99px;white-space:nowrap}.local-badge i{width:6px;height:6px;background:#44a77a;border-radius:50%}.app-content{flex:1;width:100%}.app-error{margin:20px auto 0;max-width:1320px;padding:12px 16px;background:#fff0ef;color:#a23b35;border:1px solid #f0d0cc;border-radius:9px;font-size:12px}.app-footer{display:flex;justify-content:space-between;max-width:1320px;width:calc(100% - 48px);margin:50px auto 0;padding:20px 0;border-top:1px solid var(--border);font-size:10px;color:var(--text-tertiary)}@media(max-width:760px){.app-header{height:auto;min-height:62px;padding:10px 14px;gap:12px;flex-wrap:wrap}.brand small{display:none}.brand strong{font-size:13px}.brand-mark{width:30px;height:30px;padding:7px}.local-badge{display:none}.main-nav{order:2;width:100%;height:42px;justify-content:space-between;border-top:1px solid var(--border-light)}.main-nav button{flex:1;justify-content:center;padding:0 6px;font-size:12px}.main-nav button:after{left:20%;right:20%}.app-footer{width:calc(100% - 28px)}}
</style>
