<script setup>
import { onMounted, ref, watch } from 'vue';
import { api } from '../../services/api';
import SvgIcon from '../SvgIcon.vue';
const props = defineProps({ projectId: String, episodeId: String, episodes: Array });
const emit = defineEmits(['error', 'select-episode', 'refresh']);
const readiness = ref(null); const pack = ref(null); const loading = ref(false); const error = ref(''); const expanded = ref(false);
const labels = { script_approved: '剧本已人工审批', storyboard_approved: '分镜已人工审批', images_approved: '图像审核已通过', all_shots_have_images: '所有镜头都有定稿图', character_assets_approved: '角色与场景资产已审批' };
async function load() {
  if (!props.episodeId) return;
  loading.value = true; error.value = '';
  try {
    readiness.value = await api.readiness(props.episodeId);
    pack.value = await api.productionPackage(props.episodeId);
  } catch (e) { error.value = e.message; emit('error', e.message); }
  finally { loading.value = false; }
}
async function save() {
  if (!props.episodeId) throw new Error('请选择剧集');
  const latest = await api.readiness(props.episodeId);
  return api.saveStage(props.projectId, 8, { readiness: latest, package_episode_id: props.episodeId }, props.episodeId);
}
function download() {
  const link = document.createElement('a'); link.href = api.productionPackageUrl(props.episodeId); link.download = ''; document.body.appendChild(link); link.click(); link.remove();
}
watch(() => props.episodeId, load, { immediate: true });
onMounted(load);
defineExpose({ save, load });
</script>

<template>
  <div class="ready-stage">
    <div class="ready-toolbar"><select :value="episodeId" @change="emit('select-episode', $event.target.value)"><option v-for="e in episodes" :key="e.id" :value="e.id">第 {{ e.episode_number }} 集 · {{ e.title }}</option></select><button class="btn secondary small" :disabled="loading" @click="load"><SvgIcon name="refresh" :size="15" />重新检查</button></div>
    <p v-if="error" class="error">{{ error }}</p>
    <section class="ready-overview" :class="{ complete: readiness?.ready }">
      <div class="ready-icon"><SvgIcon :name="readiness?.ready ? 'check' : 'queue'" :size="28" /></div>
      <div><p class="overline">PRODUCTION READINESS</p><h2>{{ readiness?.ready ? '本集已具备视频制作条件' : '完成最后一轮制作检查' }}</h2><p>{{ readiness?.ready ? '审批本阶段后，可下载完整 JSON 制作包。' : '这里只整理制作数据，不会生成或渲染视频。' }}</p></div>
      <span v-if="readiness" class="score">{{ Object.values(readiness.checks).filter(Boolean).length }} / {{ Object.keys(readiness.checks).length }}</span>
    </section>
    <div class="ready-grid">
      <section class="checks-panel"><div class="section-heading"><h3>交付检查</h3><span>实时结果</span></div><div v-for="(label, key) in labels" :key="key" class="check-row" :class="{ passed: readiness?.checks[key] }"><span class="check-mark"><SvgIcon :name="readiness?.checks[key] ? 'check' : 'clock'" :size="16" /></span><span>{{ label }}</span><strong>{{ readiness?.checks[key] ? '通过' : '待完成' }}</strong></div><p v-if="readiness?.missing_images?.length" class="missing">缺少定稿图：镜头 {{ readiness.missing_images.join('、') }}</p></section>
      <section class="package-panel"><div class="section-heading"><h3>制作包内容</h3><span>JSON · v1.0</span></div><div v-if="pack" class="package-stats"><div><strong>{{ pack.shots.length }}</strong><span>镜头</span></div><div><strong>{{ pack.characters.length }}</strong><span>角色</span></div><div><strong>{{ pack.scenes.length }}</strong><span>场景</span></div><div><strong>{{ pack.asset_manifest.length }}</strong><span>素材</span></div></div><ul><li>已审批剧本与剧集规划</li><li>分镜、定稿图和 Entity Linking</li><li>图像生成历史与素材清单</li><li>角色、场景及重要道具设定</li></ul><button class="btn secondary" :disabled="!pack" @click="expanded = !expanded">{{ expanded ? '收起数据预览' : '预览制作包数据' }}</button><button class="btn primary download-btn" :disabled="!readiness?.ready" @click="download"><SvgIcon name="download" :size="17" />下载 JSON 制作包</button><p v-if="!readiness?.ready" class="download-note">全部检查通过后可下载正式制作包。</p></section>
    </div>
    <pre v-if="expanded && pack" class="package-preview">{{ JSON.stringify(pack, null, 2) }}</pre>
  </div>
</template>

<style scoped>
.ready-toolbar{display:flex;justify-content:space-between;gap:12px;margin-bottom:14px}.ready-toolbar select{min-width:260px}.ready-toolbar .btn{display:flex;align-items:center;gap:6px}.ready-overview{display:flex;align-items:center;gap:18px;background:var(--surface);border:1px solid var(--border);border-radius:13px;padding:24px}.ready-overview.complete{background:#f3faf6;border-color:#cee7d9}.ready-icon{display:grid;place-items:center;width:54px;height:54px;flex-shrink:0;background:var(--accent-soft);color:var(--accent);border-radius:13px}.complete .ready-icon{background:#dff2e7;color:#28815a}.overline{font-size:10px;letter-spacing:1.5px;color:var(--accent);font-weight:700;margin:0}.ready-overview h2{font-size:21px;margin:5px 0 7px}.ready-overview p:not(.overline){font-size:13px;color:var(--text-secondary);margin:0}.score{margin-left:auto;font-size:23px;font-weight:700;color:var(--accent)}.ready-grid{display:grid;grid-template-columns:1fr 1fr;gap:15px;margin-top:15px}.checks-panel,.package-panel{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px}.section-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.section-heading h3{margin:0;font-size:16px}.section-heading span{font-size:11px;color:var(--text-secondary)}.check-row{display:flex;align-items:center;gap:10px;padding:12px 0;border-top:1px solid var(--border-light);font-size:13px}.check-mark{color:#a0a8b4;display:flex}.check-row.passed .check-mark{color:#27845a}.check-row strong{margin-left:auto;font-size:11px;font-weight:500;color:var(--text-tertiary)}.check-row.passed strong{color:#27845a}.missing{font-size:12px;color:#a15d16;background:#fff6e7;padding:10px;border-radius:7px}.package-stats{display:grid;grid-template-columns:repeat(4,1fr);padding:12px 0 18px}.package-stats div{text-align:center;border-right:1px solid var(--border)}.package-stats div:last-child{border:0}.package-stats strong,.package-stats span{display:block}.package-stats strong{font-size:23px}.package-stats span{font-size:11px;color:var(--text-secondary);margin-top:5px}.package-panel ul{padding-left:18px;color:var(--text-secondary);font-size:12px;line-height:2.1;margin:0 0 18px}.package-panel>.btn{width:100%;margin-top:8px}.download-btn{display:flex;justify-content:center;align-items:center;gap:7px}.download-note{text-align:center;color:var(--text-secondary);font-size:11px}.package-preview{margin-top:15px;padding:20px;max-height:480px;overflow:auto;background:#151b28;color:#dbe4f0;border-radius:11px;font-size:11px;line-height:1.6;white-space:pre-wrap;word-break:break-word}@media(max-width:800px){.ready-grid{grid-template-columns:1fr}}@media(max-width:550px){.ready-overview{align-items:flex-start;padding:18px}.ready-overview h2{font-size:18px}.score{display:none}.ready-toolbar{flex-wrap:wrap}.ready-toolbar select{min-width:100%;width:100%}}
</style>
