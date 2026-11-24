<script setup>
import { api } from '../../services/api';
import GalleryView from '../../views/GalleryView.vue';
const props = defineProps({ projectId: String, episodeId: String, state: Object });
const emit = defineEmits(['select-episode']);
async function save() {
  if (!props.episodeId) throw new Error('请选择剧集');
  const gallery = await api.gallery(props.episodeId);
  const content = {
    episode_id: props.episodeId,
    review_method: 'human_selected_final_images',
    shots: gallery.shots.map(shot => ({
      shot_id: shot.shot_id,
      shot_index: shot.shot_index,
      selected_image_id: shot.images.find(image => image.is_selected)?.id || null,
    })),
  };
  return api.saveStage(props.projectId, 7, content, props.episodeId);
}
defineExpose({ save });
</script>

<template>
  <div class="images-stage">
    <div class="review-guide">
      <div><strong>逐镜头选择最终画面</strong><p>生成只加入队列，不会自动通过审批。比较候选图后，点击“定为最终”完成每个镜头的人工审核。</p></div>
      <span>人工定稿</span>
    </div>
    <GalleryView
      v-if="episodeId"
      :key="episodeId"
      :project-id="projectId"
      :preferred-episode-id="episodeId"
      @select-episode="emit('select-episode', $event)"
    />
    <div v-else class="empty-images">请先在剧集规划阶段创建并选择一集。</div>
  </div>
</template>

<style scoped>
.review-guide{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:15px 18px;background:var(--accent-soft);border:1px solid #dfe3fa;border-radius:11px;margin-bottom:16px}.review-guide strong{font-size:14px}.review-guide p{margin:5px 0 0;font-size:12px;color:var(--text-secondary);line-height:1.6}.review-guide>span{flex-shrink:0;font-size:11px;color:var(--accent);background:var(--surface);padding:5px 10px;border-radius:99px}.empty-images{padding:90px;text-align:center;color:var(--text-secondary);border:1px dashed var(--border-strong);border-radius:12px}.images-stage :deep(.panel){margin-top:12px}.images-stage :deep(.shot-list){margin-top:16px}.images-stage :deep(.shot-card){background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:18px}.images-stage :deep(.shot-progress-meta){color:var(--text-secondary)}.images-stage :deep(.shot-progress-meta strong){color:var(--accent)}.images-stage :deep(.shot-progress-track){background:#e7eaf0}.images-stage :deep(.shot-progress-track div){background:var(--accent)}.images-stage :deep(.img-box){background:var(--surface);border:1px solid var(--border);width:min(300px,100%)}.images-stage :deep(.img-box.selected){border-color:#34a474;box-shadow:0 0 0 1px #34a474}.images-stage :deep(.img-box img){background:#eef1f5;aspect-ratio:16/9;object-fit:cover}.images-stage :deep(.star){color:#25855a}.images-stage :deep(.badge.running){background:#fff4d9;color:#9a6410}.images-stage :deep(.fail-box){background:#fff3f2;border-color:#f0c8c4}.images-stage :deep(.ref-chip){background:var(--accent-soft);color:var(--accent)}.images-stage :deep(.prompt-editor){border-color:var(--border)}.images-stage :deep(.meta-table){color:var(--text-secondary)}.images-stage :deep(.meta-table td){border-color:var(--border)}.images-stage :deep(.modal){background:var(--surface)}.images-stage :deep(.modal .row){display:flex;gap:10px;justify-content:flex-end;margin-top:18px}@media(max-width:650px){.review-guide{align-items:flex-start}.review-guide>span{display:none}.images-stage :deep(.img-box){width:100%}}
</style>
