import axios from "axios";

export const api = axios.create({
  baseURL: "/api",
  headers: {
    "Content-Type": "application/json",
  },
});

export interface SystemStatus {
  is_processing: boolean;
  is_paused: boolean;
  pause_requested: boolean;
  auto_shutdown: boolean;
  current_index: number;
  queue: QueueItem[];
  workers: {
    gui: string;
    preprocess: string;
  };
  buffer_status: Record<string, { owner_video: string; owner_status: string; occupied: boolean }>;
}

export interface QueueItem {
  id?: string;
  project_name?: string;
  video_name?: string;
  video?: string;
  folder?: string;
  mode?: "translate_only" | "full_pipeline" | "full_publish" | string;
  mode_label?: string;
  config?: Record<string, any>;
  status: "pending" | "running" | "failed" | "success" | "preprocessing" | "gui_processing" | "ready_for_capcut" | "paused" | string;
  progress?: number;
  duration?: string;
  message?: string;
  details?: string;
}

export interface PipelineProject {
  Folder: string;
  ProjectName: string;
  TotalVideos: number;
  SizeMB: number;
  DurationSec: number;
  CoverImage: string;
  HasConfig: boolean;
}

export interface ProjectConfigPayload {
  video_path?: string;
  video_paths?: string[];
  speed?: number;
  volume_db?: number;
  tts_speed?: number;
  tts_engine?: string;
  font_size?: number;
  font_color?: string;
  font_name?: string;
  translation_method?: string;
  translation_ai_profile_id?: string;
  context_ai_profile_id?: string;
  source_language?: string;
  target_language?: string;
  ai_tone?: string;
  video_context?: string;
  ai_temperature?: number;
  enable_anti_copyright?: boolean;
  mirror_video?: boolean;
  hardsub_blur_enabled?: boolean;
  use_local_ocr?: boolean;
  use_local_whisper?: boolean;
  filter_audio?: boolean;
  ocr_crop_mode?: string;
  ocr_crop_x?: number;
  ocr_crop_y?: number;
  ocr_crop_w?: number;
  ocr_crop_h?: number;
  whisper_subtitle_offset_ms?: number;
  whisper_model?: string;
  whisper_vad_filter?: boolean;
  canvas_ratio?: string;
  width?: number;
  height?: number;
  [key: string]: any;
}

export const fetchSystemStatus = async (): Promise<SystemStatus> => {
  const res = await api.get("/status");
  return res.data;
};

export interface UIConnectionResult {
  ok: boolean;
  message?: string;
  error?: string;
  window?: string;
  status?: string;
}

export const testUIConnection = async (): Promise<UIConnectionResult> => {
  const res = await api.post("/test_connection");
  return res.data;
};

export const toggleAutoShutdown = async (): Promise<{ ok: boolean; auto_shutdown: boolean }> => {
  const res = await api.post("/auto_shutdown");
  return res.data;
};

export const fetchPipelineProjects = async (): Promise<PipelineProject[]> => {
  const res = await api.get("/pipeline-projects");
  const rawList = res.data.projects || res.data || [];
  return rawList.map((p: any) => ({
    Folder: p.Folder || p.id || p.folder || p.project_name || p.name || "",
    ProjectName: p.ProjectName || p.name || p.project_name || p.id || p.folder || "",
    TotalVideos: p.TotalVideos ?? p.total_videos ?? 0,
    SizeMB: p.SizeMB ?? p.size_mb ?? 0,
    DurationSec: p.DurationSec ?? p.duration_sec ?? 0,
    CoverImage: p.CoverImage || p.cover_image || "",
    HasConfig: p.HasConfig ?? p.has_config ?? false,
  }));
};

export const createPipelineProject = async (projectName: string): Promise<{ ok: boolean; folder?: string; error?: string }> => {
  const res = await api.post("/pipeline-projects/create", { name: projectName, project_name: projectName });
  const data = res.data;
  return {
    ok: data.ok ?? true,
    folder: data.folder || data.id || projectName,
    error: data.error,
  };
};

export const fetchProjectConfig = async (folder: string): Promise<ProjectConfigPayload> => {
  const res = await api.get(`/pipeline-projects/${encodeURIComponent(folder)}/config`);
  return res.data.config || res.data || {};
};

export const saveProjectConfig = async (folder: string, config: ProjectConfigPayload): Promise<{ ok: boolean; error?: string }> => {
  const res = await api.post(`/pipeline-projects/${encodeURIComponent(folder)}/config`, config);
  return res.data;
};

export const runProjectPipeline = async (folder: string): Promise<{ ok: boolean; queue?: any[]; error?: string }> => {
  try {
    const addRes = await api.post("/queue/add", { folder, project_name: folder, replace_queue: false });
    try {
      await api.post("/start", { auto_shutdown: false });
    } catch (startErr) {
      console.warn("Queue start call warning:", startErr);
    }
    return { ok: true, queue: addRes.data?.queue || [] };
  } catch (err: any) {
    return { ok: false, error: err.response?.data?.error || err.message || String(err) };
  }
};

export const fetchSocialSettings = async (): Promise<any> => {
  const res = await api.get("/social_settings");
  return res.data.settings || res.data || {};
};

export const saveSocialSettings = async (settings: any): Promise<{ ok: boolean; error?: string }> => {
  const res = await api.post("/social_settings", settings);
  return res.data;
};

export const fetchGlobalSettings = async (): Promise<any> => {
  const res = await api.get("/settings/global");
  return res.data.settings || res.data || {};
};

export const saveGlobalSettings = async (settings: any): Promise<{ ok: boolean; error?: string }> => {
  const res = await api.post("/settings/global", settings);
  return res.data;
};

// Storage & Database Management APIs
export const fetchStorageStatus = async (): Promise<any> => {
  const res = await api.get("/system/storage_status");
  return res.data;
};

export const triggerCleanupCache = async (keepRecent: number = 1, dryRun: boolean = false): Promise<any> => {
  const res = await api.post("/system/cleanup_cache", {
    keep_recent_uploads: keepRecent,
    dry_run: dryRun,
  });
  return res.data;
};

// Queue Management API
export const startQueue = async () => (await api.post("/start")).data;
export const pauseQueue = async () => (await api.post("/pause")).data;
export const resumeQueue = async () => (await api.post("/resume")).data;
export const clearQueue = async () => (await api.post("/clear")).data;
export const deleteQueueItem = async (index: number) => (await api.post("/queue/delete", { index })).data;
export const retryQueueItem = async (index: number) => (await api.post("/queue/retry", { index })).data;
export const cancelQueueItem = async (index: number) => (await api.post("/queue/cancel", { index })).data;

// Native OS File Picker APIs
export const selectNativeFiles = async (): Promise<string[]> => {
  const res = await api.post("/select_files");
  return res.data.files || [];
};

export const selectNativeFolder = async (): Promise<string> => {
  const res = await api.post("/select_folder");
  return res.data.folder || res.data.path || "";
};

// Social Multi-Platform Publishing API (/api/v1/...)
export interface PublishSocialPayload {
  file_path?: string;
  video_url?: string;
  title: string;
  description?: string;
  platforms: string[];
  privacy_status?: "public" | "unlisted" | "private";
  tags?: string[];
  thumbnail_file?: string;
  category_id?: string;
  made_for_kids?: boolean;
}

export interface ScheduleSocialPayload extends PublishSocialPayload {
  scheduled_at: string; // ISO string e.g. "2026-08-18T19:00:00"
}

export const publishSocialVideo = async (payload: PublishSocialPayload): Promise<any> => {
  const res = await axios.post("/api/v1/publish", payload);
  return res.data;
};

export const scheduleSocialVideo = async (payload: ScheduleSocialPayload): Promise<any> => {
  const res = await axios.post("/api/v1/schedule", payload);
  return res.data;
};

export const fetchScheduledPosts = async (): Promise<any[]> => {
  const res = await axios.get("/api/v1/schedules");
  return res.data.schedules || [];
};

export const deleteScheduledPost = async (scheduleId: string): Promise<any> => {
  const res = await axios.delete(`/api/v1/schedules/${encodeURIComponent(scheduleId)}`);
  return res.data;
};

export const fetchSocialJobs = async (): Promise<any[]> => {
  const res = await axios.get("/api/v1/jobs");
  return res.data.jobs || [];
};

export const fetchSocialStatus = async (): Promise<any> => {
  const res = await axios.get("/api/v1/status");
  return res.data;
};

// =========================================================================
// CLOUD ASSET REGISTRY & DOWNLOAD APIS (5TB Google Drive & MongoDB Atlas)
// =========================================================================

export interface CloudAsset {
  asset_id: string;
  novel_id: string;
  novel_title: string;
  episode: number;
  category: "video_raw" | "scene_analysis" | "keyframes" | "srt_subtitles" | "audio_tts" | "rendered_video" | "script" | "visuals_dataset" | "other";
  filename: string;
  relative_path: string;
  drive_path: string;
  size_bytes: number;
  size_mb: number;
  mime_type: string;
  created_at: number;
  metadata?: Record<string, any>;
  download_url: string;
}

export interface CloudEpisodeBundle {
  bundle_key: string;
  novel_id: string;
  novel_title: string;
  episode: number;
  total_files: number;
  total_size_mb: number;
  has_raw_video: boolean;
  raw_video_filename: string;
  has_scenes_analysis: boolean;
  scenes_count: number;
  has_subtitles: boolean;
  srt_filename: string;
  keyframes_count: number;
  has_script: boolean;
  has_audio: boolean;
  has_rendered_video: boolean;
  preview_thumbnail: string;
  assets: CloudAsset[];
}

export interface CloudManifest {
  version: string;
  last_scanned_at: number;
  drive_root: string;
  total_assets: number;
  total_size_mb: number;
  total_size_gb: number;
  categories_count: Record<string, number>;
  assets: CloudAsset[];
}

export const fetchCloudAssets = async (params?: {
  category?: string;
  novel_id?: string;
  episode?: number;
  search?: string;
  limit?: number;
}): Promise<{ success: boolean; count: number; assets: CloudAsset[] }> => {
  const res = await axios.get("/api/cloud/assets", { params });
  return res.data;
};

export const fetchCloudEpisodes = async (novel_id?: string): Promise<{
  success: boolean;
  count: number;
  episodes: CloudEpisodeBundle[];
}> => {
  const res = await axios.get("/api/cloud/assets/episodes", { params: { novel_id } });
  return res.data;
};

export const fetchCloudManifest = async (): Promise<{ success: boolean; manifest: CloudManifest }> => {
  const res = await axios.get("/api/cloud/assets/manifest");
  return res.data;
};

export const rescanCloudAssets = async (): Promise<{ success: boolean; message: string; manifest: CloudManifest }> => {
  const res = await axios.post("/api/cloud/assets/rescan");
  return res.data;
};

export const getCloudDownloadUrl = (asset_id_or_rel: string): string => {
  if (asset_id_or_rel.startsWith("scene_analysis/") || asset_id_or_rel.includes("/")) {
    return `/api/cloud/download?relative_path=${encodeURIComponent(asset_id_or_rel)}`;
  }
  return `/api/cloud/download?asset_id=${encodeURIComponent(asset_id_or_rel)}`;
};

export const getEpisodeBundleDownloadUrl = (novel_id: string, episode: number, include_video: boolean = false): string => {
  return `/api/cloud/download_bundle?novel_id=${encodeURIComponent(novel_id)}&episode=${episode}&include_video=${include_video}`;
};

export const pullCloudAssetToLocal = async (asset_id: string): Promise<any> => {
  const res = await axios.post("/api/cloud/pull_to_local", { asset_id });
  return res.data;
};

