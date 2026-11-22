const BASE = "http://127.0.0.1:8000";
const API = BASE + "/api/v1";

async function req(path, options = {}) {
  const r = await fetch(API + path, options);
  if (!r.ok) {
    let msg = r.statusText;
    try {
      const d = await r.json();
      msg = typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail);
    } catch {}
    throw new Error(msg);
  }
  return r.json();
}

const json = (method, path, body) =>
  req(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const api = {
  // Phase 1：小说生成剧本（不在 /api/v1 下）
  async generate(novel) {
    const r = await fetch(BASE + "/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ novel }),
    });
    const d = await r.json();
    if (!r.ok)
      throw new Error(
        typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail)
      );
    return d;
  },

  // Projects
  listProjects: () => req("/projects"),
  createProject: (data) => json("POST", "/projects", data),
  updateProject: (id, data) => json("PUT", `/projects/${id}`, data),
  deleteProject: (id) => req(`/projects/${id}`, { method: "DELETE" }),

  // Characters
  listCharacters: (pid) => req(`/projects/${pid}/characters`),
  createCharacter: (pid, data) => json("POST", `/projects/${pid}/characters`, data),
  updateCharacter: (id, data) => json("PUT", `/characters/${id}`, data),
  deleteCharacter: (id) => req(`/characters/${id}`, { method: "DELETE" }),
  uploadCharacterRef: (id, file) => {
    const fd = new FormData();
    fd.append("file", file);
    return req(`/characters/${id}/reference-image`, { method: "POST", body: fd });
  },

  // Scenes
  listScenes: (pid) => req(`/projects/${pid}/scenes`),
  createScene: (pid, data) => json("POST", `/projects/${pid}/scenes`, data),
  updateScene: (id, data) => json("PUT", `/scenes/${id}`, data),
  deleteScene: (id) => req(`/scenes/${id}`, { method: "DELETE" }),
  uploadSceneRef: (id, file) => {
    const fd = new FormData();
    fd.append("file", file);
    return req(`/scenes/${id}/reference-image`, { method: "POST", body: fd });
  },

  // Assets
  listAssets: (pid) => req(`/projects/${pid}/assets`),
  deleteAsset: (id) => req(`/assets/${id}`, { method: "DELETE" }),
  assetFileUrl: (id) => `${API}/assets/${id}/file`,

  // Extraction
  extract: (pid, novel) => json("POST", `/projects/${pid}/extract`, { novel }),
  confirmExtraction: (id, draft) =>
    json("POST", `/extractions/${id}/confirm`, { draft }),

  // Episodes & Entity Linking（Phase 2.5）
  listEpisodes: (pid) => req(`/projects/${pid}/episodes`),
  getEpisode: (id) => req(`/episodes/${id}`),
  generateEpisode: (pid, novel) =>
    json("POST", `/projects/${pid}/episodes/generate`, { novel }),
  linkEntities: (eid) => req(`/episodes/${eid}/link-entities`, { method: "POST" }),
  episodeLinks: (eid) => req(`/episodes/${eid}/entity-links`),
  setShotLinks: (sid, links) => json("PUT", `/shots/${sid}/entity-links`, { links }),
  getShotLinks: (sid) => req(`/shots/${sid}/entity-links`),
  resolveEntity: (sid, data) => json("POST", `/shots/${sid}/resolve-entity`, data),
  generationContext: (sid) => req(`/shots/${sid}/generation-context`),

  // Image Generation（Stage 3）
  generateShot: (sid, data = { variations: 2 }) =>
    json("POST", `/shots/${sid}/generate`, data),
  generateAll: (eid, data = { variations: 1 }) =>
    json("POST", `/episodes/${eid}/generate-all`, data),
  generateCharacter: (id) => req(`/characters/${id}/generate`, { method: "POST" }),
  generateScene: (id) => req(`/scenes/${id}/generate`, { method: "POST" }),
  gallery: (eid) => req(`/episodes/${eid}/gallery`),
  listJobs: (pid, status) =>
    req(`/projects/${pid}/generation-jobs${status ? `?status=${status}` : ""}`),
  cancelJob: (jid) => req(`/generation-jobs/${jid}/cancel`, { method: "POST" }),
  retryJob: (jid) => req(`/generation-jobs/${jid}/retry`, { method: "POST" }),
  selectImage: (iid) => req(`/shot-images/${iid}/select`, { method: "POST" }),

  // Sprint 6.5：Prompt 编辑与重新生成
  getShotPrompt: (sid) => req(`/shots/${sid}/prompt`),
  saveShotPrompt: (sid, data) => json("PUT", `/shots/${sid}/prompt`, data),
  regenerateShot: (sid, data) => json("POST", `/shots/${sid}/regenerate`, data),

  // Production Management System
  dashboard: () => req("/dashboard"),
  workflow: (pid) => req(`/projects/${pid}/workflow`),
  stage: (pid, stage, episodeId) => req(`/projects/${pid}/workflow/${stage}${episodeId ? `?episode_id=${episodeId}` : ""}`),
  saveStage: (pid, stage, content, episodeId) => json("PUT", `/projects/${pid}/workflow/${stage}${episodeId ? `?episode_id=${episodeId}` : ""}`, content),
  generateStage: (pid, stage, episodeId) => req(`/projects/${pid}/workflow/${stage}/generate${episodeId ? `?episode_id=${episodeId}` : ""}`, { method: "POST" }),
  reviewStage: (pid, stage, episodeId) => req(`/projects/${pid}/workflow/${stage}/review${episodeId ? `?episode_id=${episodeId}` : ""}`, { method: "POST" }),
  approveStage: (pid, stage, episodeId) => req(`/projects/${pid}/workflow/${stage}/approve${episodeId ? `?episode_id=${episodeId}` : ""}`, { method: "POST" }),
  rejectStage: (pid, stage, episodeId) => req(`/projects/${pid}/workflow/${stage}/reject${episodeId ? `?episode_id=${episodeId}` : ""}`, { method: "POST" }),
  resumeProject: (pid, stage, episodeId) => json("POST", `/projects/${pid}/resume`, { stage, episode_id: episodeId || null }),
  importNovel: (pid, name, text) => json("POST", `/projects/${pid}/novel`, { name, text }),
  uploadNovel: (pid, file) => {
    const fd = new FormData(); fd.append("file", file);
    return req(`/projects/${pid}/novel/import`, { method: "POST", body: fd });
  },
  revisions: (stateId) => req(`/production-states/${stateId}/revisions`),
  updateShotProduction: (sid, data) => json("PUT", `/shots/${sid}/production`, data),
  duplicateShot: (sid) => req(`/shots/${sid}/duplicate`, { method: "POST" }),
  reorderShots: (eid, ids) => json("PUT", `/episodes/${eid}/shots/reorder`, ids),
  storyboardQuality: (eid) => req(`/episodes/${eid}/storyboard-quality`),
  readiness: (eid) => req(`/episodes/${eid}/readiness`),
  productionPackage: (eid) => req(`/episodes/${eid}/production-package`),
  productionPackageUrl: (eid) => `${API}/episodes/${eid}/production-package/download`,
};
