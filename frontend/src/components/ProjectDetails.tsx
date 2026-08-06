import React, { useState, useEffect, useRef } from "react";
import { toast } from "sonner";
import {
  ArrowLeft,
  Play,
  Film,
  MessageSquare,
  Globe,
  Sparkles,
  CheckCircle2,
  Shield,
  Eye,
  Volume2,
  Type,
  FolderOpen,
  Wand2,
  Thermometer,
  Languages,
} from "lucide-react";
import {
  fetchProjectConfig,
  saveProjectConfig,
  runProjectPipeline,
  fetchGlobalSettings,
  selectNativeFiles,
} from "../lib/api";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Badge } from "./ui/badge";
import { Input } from "./ui/input";

interface ProjectDetailsProps {
  folder: string;
  onBack: () => void;
  onRunSuccess?: () => void;
}

export const ProjectDetails: React.FC<ProjectDetailsProps> = ({ folder, onBack, onRunSuccess }) => {
  const [activeTab, setActiveTab] = useState<"video" | "sub" | "translate" | "all">("video");
  const [globalProfiles, setGlobalProfiles] = useState<any[]>([]);

  const [config, setConfig] = useState<any>({
    video_path: "",
    video_paths: [],
    speed: 0.77,
    volume_db: -15.5,
    tts_speed: 1.17,
    tts_engine: "local",
    font_size: 15.0,
    font_color: "#f0ff00",
    font_name: "C:/Users/nguye/AppData/Local/CapCut/Apps/8.9.1.3802/Resources/Font/SystemFont/en.ttf",
    translation_method: "ai",
    translation_ai_profile_id: "",
    context_ai_profile_id: "",
    source_language: "Chinese",
    target_language: "Vietnamese",
    ai_tone: "natural and fluent",
    video_context: "Short fantasy game online videos, MMORPG gameplay review, PvP server war",
    ai_temperature: 0.0,
    enable_anti_copyright: true,
    mirror_video: false,
    hardsub_blur_enabled: true,
    use_local_ocr: false,
    use_local_whisper: true,
    filter_audio: false,
    ocr_crop_mode: "auto",
    ocr_crop_x: 0,
    ocr_crop_y: 0,
    ocr_crop_w: 0,
    ocr_crop_h: 0,
    whisper_subtitle_offset_ms: 0,
    whisper_model: "large-v3",
    whisper_vad_filter: true,
    canvas_ratio: "16:9",
  });

  const [saveMessage, setSaveMessage] = useState<string>("");
  const autoSaveTimeout = useRef<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [pData, gData] = await Promise.all([
          fetchProjectConfig(folder),
          fetchGlobalSettings(),
        ]);

        if (gData && Array.isArray(gData.ai_profiles)) {
          setGlobalProfiles(gData.ai_profiles);
        }

        if (pData && Object.keys(pData).length > 0) {
          const profiles = gData?.ai_profiles || pData.available_ai_profiles || [];
          const defaultProfId = profiles[0]?.id || "openai-default";

          setConfig((prev: any) => ({
            ...prev,
            ...pData,
            video_path: pData.video_path || (pData.video_paths ? pData.video_paths.join("\n") : ""),
            translation_ai_profile_id: pData.translation_ai_profile_id || pData.default_translation_ai_profile_id || defaultProfId,
            context_ai_profile_id: pData.context_ai_profile_id || pData.default_context_ai_profile_id || defaultProfId,
          }));
        }
      } catch (err) {
        console.error("Lỗi đọc cấu hình dự án & global settings", err);
      }
    };
    loadData();
  }, [folder]);

  const triggerAutoSave = (newConfig: any) => {
    setConfig(newConfig);
    setSaveMessage("Đang tự động lưu...");
    if (autoSaveTimeout.current) clearTimeout(autoSaveTimeout.current);

    autoSaveTimeout.current = setTimeout(async () => {
      try {
        const payload = {
          ...newConfig,
          video_paths: newConfig.video_path ? newConfig.video_path.split(/\r?\n|;/).map((v: string) => v.trim()).filter(Boolean) : [],
        };
        await saveProjectConfig(folder, payload);
        setSaveMessage("Đã lưu tự động");
      } catch (err) {
        setSaveMessage("Lỗi khi lưu");
      } finally {
        setTimeout(() => setSaveMessage(""), 2000);
      }
    }, 400);
  };

  const handleFieldChange = (key: string, value: any) => {
    const updated = { ...config, [key]: value };
    triggerAutoSave(updated);
  };

  const handleFilePickerClick = () => {
    fileInputRef.current?.click();
  };

  const handleSelectNativeFiles = async () => {
    try {
      const files = await selectNativeFiles();
      if (files && files.length > 0) {
        const existing = config.video_path ? config.video_path.trim() : "";
        const newContent = existing ? `${existing}\n${files.join("\n")}` : files.join("\n");
        handleFieldChange("video_path", newContent);
        toast.success(`Đã chọn ${files.length} file video!`);
      }
    } catch (err) {
      toast.error("Lỗi khi mở Tkinter picker", { description: String(err) });
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const paths: string[] = [];
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const filePath = (file as any).path || file.name;
      paths.push(filePath);
    }

    const existing = config.video_path ? config.video_path.trim() : "";
    const newContent = existing ? `${existing}\n${paths.join("\n")}` : paths.join("\n");
    handleFieldChange("video_path", newContent);
    toast.success(`Đã chọn ${files.length} file video vào danh sách!`);
    if (e.target) e.target.value = "";
  };

  const handleRunPipeline = async () => {
    const videoPaths = config.video_path ? config.video_path.split(/\r?\n|;/).map((v: string) => v.trim()).filter(Boolean) : [];
    if (videoPaths.length === 0) {
      toast.error("Chưa chọn video đầu vào!", {
        description: "Vui lòng nhập đường dẫn hoặc bấm '📂 Chọn file' để thêm video trước khi chạy Pipeline.",
      });
      return;
    }

    try {
      const payload = {
        ...config,
        video_paths: videoPaths,
      };
      await saveProjectConfig(folder, payload);
      const res = await runProjectPipeline(folder);
      if (res.ok) {
        toast.success(`Đã đưa dự án ${folder} vào hàng chờ và khởi chạy thành công!`);
        if (onRunSuccess) {
          onRunSuccess();
        } else {
          onBack();
        }
      } else {
        toast.error("Lỗi khi chạy pipeline", { description: res.error || "Không xác định" });
      }
    } catch (err: any) {
      toast.error("Lỗi gọi API", { description: err.message || String(err) });
    }
  };

  const selectedTransProfile = globalProfiles.find((p) => p.id === config.translation_ai_profile_id);
  const selectedContextProfile = globalProfiles.find((p) => p.id === config.context_ai_profile_id);

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <Card className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 border-cyan-500/30">
        <div className="flex items-center gap-4">
          <Button variant="secondary" size="sm" onClick={onBack}>
            <ArrowLeft className="w-3.5 h-3.5 mr-1" />
            <span>Back to Projects</span>
          </Button>
          <div>
            <h2 className="text-lg font-extrabold text-cyan-400">
              Chi tiết dự án: {folder}
            </h2>
            <div className="flex items-center gap-3 text-xs text-muted-foreground font-mono mt-0.5">
              <span>Thư mục: <strong className="text-cyan-300">{folder}</strong></span>
              {saveMessage && (
                <Badge variant="success">
                  <CheckCircle2 className="w-3 h-3 mr-1" /> {saveMessage}
                </Badge>
              )}
            </div>
          </div>
        </div>
      </Card>

      {/* Tabs Bar */}
      <div className="flex items-center gap-2 p-1.5 glass-panel border-white/10 overflow-x-auto">
        <Button
          variant={activeTab === "video" ? "default" : "ghost"}
          size="sm"
          onClick={() => setActiveTab("video")}
        >
          <Film className="w-4 h-4 mr-1.5" /> 🎬 Video & Xử lý (Step 1–2)
        </Button>
        <Button
          variant={activeTab === "sub" ? "default" : "ghost"}
          size="sm"
          onClick={() => setActiveTab("sub")}
        >
          <MessageSquare className="w-4 h-4 mr-1.5" /> 📝 Phụ đề & Whisper (Step 3, 5–7)
        </Button>
        <Button
          variant={activeTab === "translate" ? "default" : "ghost"}
          size="sm"
          onClick={() => setActiveTab("translate")}
        >
          <Globe className="w-4 h-4 mr-1.5" /> 🌐 Dịch thuật & AI (Step 4)
        </Button>
        <Button
          variant={activeTab === "all" ? "default" : "ghost"}
          size="sm"
          onClick={() => setActiveTab("all")}
        >
          <Sparkles className="w-4 h-4 mr-1.5" /> ⚡ Tất cả cài đặt
        </Button>
      </div>

      {/* Form Content */}
      <Card className="p-6 space-y-8">
        {(activeTab === "video" || activeTab === "all") && (
          <div className="space-y-4 pb-6 border-b border-white/10">
            <h3 className="text-sm font-bold text-cyan-400 flex items-center gap-2">
              <Film className="w-4 h-4" /> Step 1-2: Video đầu vào & Canvas Ratio
            </h3>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-xs font-semibold text-muted-foreground">
                  Danh sách file Video (đường dẫn tuyệt đối từng dòng):
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="file"
                    multiple
                    accept="video/*,.mp4,.mov,.mkv,.avi,.webm"
                    ref={fileInputRef}
                    onChange={handleFileSelect}
                    className="hidden"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleFilePickerClick}
                    className="h-7 text-xs border-cyan-500/40 text-cyan-300 bg-cyan-500/10 hover:bg-cyan-500/20"
                  >
                    <FolderOpen className="w-3.5 h-3.5 mr-1 text-cyan-400" /> 📂 Chọn file
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleSelectNativeFiles}
                    className="h-7 text-xs border-purple-500/40 text-purple-300 bg-purple-500/10 hover:bg-purple-500/20"
                  >
                    <FolderOpen className="w-3.5 h-3.5 mr-1 text-purple-400" /> 🖥️ OS Tkinter Picker
                  </Button>
                </div>
              </div>
              <textarea
                rows={3}
                value={config.video_path || ""}
                onChange={(e) => handleFieldChange("video_path", e.target.value)}
                placeholder="C:\Videos\sample1.mp4&#10;C:\Videos\sample2.mp4"
                className="w-full px-3 py-2 text-xs bg-black/40 border border-white/10 rounded-xl text-foreground font-mono focus:outline-none focus:border-cyan-400"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1">
                  Tốc độ Video:
                </label>
                <Input
                  type="number"
                  step="0.01"
                  value={config.speed ?? 0.77}
                  onChange={(e) => handleFieldChange("speed", parseFloat(e.target.value))}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1 flex items-center gap-1">
                  <Volume2 className="w-3.5 h-3.5 text-cyan-400" /> Âm lượng (dB):
                </label>
                <Input
                  type="number"
                  step="0.1"
                  value={config.volume_db ?? -15.5}
                  onChange={(e) => handleFieldChange("volume_db", parseFloat(e.target.value))}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1">
                  Khung hình (Canvas Aspect Ratio):
                </label>
                <select
                  value={config.canvas_ratio || "16:9"}
                  onChange={(e) => handleFieldChange("canvas_ratio", e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-black/40 border border-white/10 rounded-xl text-foreground"
                >
                  <option value="16:9">🖥️ 16:9 — Ngang (1920×1080)</option>
                  <option value="9:16">📱 9:16 — Dọc (1080×1920)</option>
                  <option value="1:1">⬛ 1:1 — Vuông (1080×1080)</option>
                  <option value="4:3">📺 4:3 — Cổ điển (1440×1080)</option>
                </select>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-6 pt-2">
              <label className="flex items-center gap-2 text-xs font-semibold cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.enable_anti_copyright ?? true}
                  onChange={(e) => handleFieldChange("enable_anti_copyright", e.target.checked)}
                  className="rounded border-white/20 bg-black/40 text-cyan-400 focus:ring-0"
                />
                <span className="flex items-center gap-1"><Shield className="w-3.5 h-3.5 text-cyan-400" /> Lách bản quyền động (Smart Defense)</span>
              </label>

              <label className="flex items-center gap-2 text-xs font-semibold cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.mirror_video ?? false}
                  onChange={(e) => handleFieldChange("mirror_video", e.target.checked)}
                  className="rounded border-white/20 bg-black/40 text-cyan-400 focus:ring-0"
                />
                <span>🪞 Mirror Video (Lật ngang)</span>
              </label>

              <label className="flex items-center gap-2 text-xs font-semibold cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.hardsub_blur_enabled ?? true}
                  onChange={(e) => handleFieldChange("hardsub_blur_enabled", e.target.checked)}
                  className="rounded border-white/20 bg-black/40 text-cyan-400 focus:ring-0"
                />
                <span className="flex items-center gap-1"><Eye className="w-3.5 h-3.5 text-purple-400" /> Làm mờ Hardsub</span>
              </label>

              <label className="flex items-center gap-2 text-xs font-semibold cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.filter_audio ?? false}
                  onChange={(e) => handleFieldChange("filter_audio", e.target.checked)}
                  className="rounded border-white/20 bg-black/40 text-emerald-400 focus:ring-0"
                />
                <span className="flex items-center gap-1">
                  <Wand2 className="w-3.5 h-3.5 text-emerald-400" /> 🧹 Lọc âm gốc (Demucs + DeepFilter)
                </span>
              </label>
            </div>
          </div>
        )}

        {(activeTab === "sub" || activeTab === "all") && (
          <div className="space-y-4 pb-6 border-b border-white/10">
            <h3 className="text-sm font-bold text-purple-400 flex items-center gap-2">
              <MessageSquare className="w-4 h-4" /> Step 3, 5-7: Phụ đề, Whisper GPU & TTS
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1">
                  Model Whisper:
                </label>
                <select
                  value={config.whisper_model || "large-v3"}
                  onChange={(e) => handleFieldChange("whisper_model", e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-black/40 border border-white/10 rounded-xl text-foreground"
                >
                  <option value="large-v3">large-v3 ★</option>
                  <option value="large-v3-turbo">large-v3-turbo</option>
                  <option value="medium">medium</option>
                  <option value="small">small</option>
                  <option value="base">base</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1">
                  Engine TTS:
                </label>
                <select
                  value={config.tts_engine || "local"}
                  onChange={(e) => handleFieldChange("tts_engine", e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-black/40 border border-white/10 rounded-xl text-foreground"
                >
                  <option value="local">NGHI-TTS (Offline Fast)</option>
                  <option value="capcut">CapCut GUI Voice</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1">
                  Tốc độ TTS:
                </label>
                <Input
                  type="number"
                  step="0.01"
                  value={config.tts_speed ?? 1.17}
                  onChange={(e) => handleFieldChange("tts_speed", parseFloat(e.target.value))}
                />
              </div>
            </div>

            {/* Subtitle Font Customization */}
            <div className="p-4 rounded-xl bg-black/30 border border-white/10 space-y-3">
              <h4 className="text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                <Type className="w-3.5 h-3.5" /> Định dạng phông chữ Phụ đề (Subtitle Style)
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-[11px] font-medium text-muted-foreground mb-1">Font chữ (Đường dẫn absolute):</label>
                  <Input
                    type="text"
                    value={config.font_name || "C:/Users/nguye/AppData/Local/CapCut/Apps/8.9.1.3802/Resources/Font/SystemFont/en.ttf"}
                    onChange={(e) => handleFieldChange("font_name", e.target.value)}
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-muted-foreground mb-1">Cỡ chữ Sub (font_size):</label>
                  <Input
                    type="number"
                    step="0.5"
                    value={config.font_size ?? 15.0}
                    onChange={(e) => handleFieldChange("font_size", parseFloat(e.target.value))}
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-muted-foreground mb-1">Màu chữ (font_color):</label>
                  <select
                    value={config.font_color || "#f0ff00"}
                    onChange={(e) => handleFieldChange("font_color", e.target.value)}
                    className="w-full px-3 py-2 text-xs bg-black/40 border border-white/10 rounded-xl text-foreground"
                  >
                    <option value="#f0ff00">🟡 Vàng preset (#f0ff00)</option>
                    <option value="#FFFF00">🟡 Vàng thuần (#FFFF00)</option>
                    <option value="#FFFFFF">⬜ Trắng (#FFFFFF)</option>
                    <option value="#FF0000">🔴 Đỏ (#FF0000)</option>
                    <option value="#00FF00">🟢 Xanh Lá (#00FF00)</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-6 pt-2">
              <label className="flex items-center gap-2 text-xs font-semibold cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.use_local_whisper ?? true}
                  onChange={(e) => handleFieldChange("use_local_whisper", e.target.checked)}
                  className="rounded border-white/20 bg-black/40 text-purple-400 focus:ring-0"
                />
                <span>Whisper GPU (Local GPU khuyên dùng)</span>
              </label>

              <label className="flex items-center gap-2 text-xs font-semibold cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.use_local_ocr ?? false}
                  onChange={(e) => handleFieldChange("use_local_ocr", e.target.checked)}
                  className="rounded border-white/20 bg-black/40 text-purple-400 focus:ring-0"
                />
                <span>PaddleOCR (Quét chữ từ frame)</span>
              </label>

              <label className="flex items-center gap-2 text-xs font-semibold cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.whisper_vad_filter ?? true}
                  onChange={(e) => handleFieldChange("whisper_vad_filter", e.target.checked)}
                  className="rounded border-white/20 bg-black/40 text-purple-400 focus:ring-0"
                />
                <span>VAD Filter (Lọc ảo giác)</span>
              </label>
            </div>
          </div>
        )}

        {(activeTab === "translate" || activeTab === "all") && (
          <div className="space-y-5 pb-6 border-b border-white/10">
            <h3 className="text-sm font-bold text-amber-400 flex items-center gap-2">
              <Globe className="w-4 h-4" /> Step 4: Dịch phụ đề & AI Context
            </h3>

            {/* Form Row 1: Translation Method & AI Translation Profile */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1">
                  Nguồn dịch (translation_method):
                </label>
                <select
                  value={config.translation_method || "google"}
                  onChange={(e) => handleFieldChange("translation_method", e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-black/40 border border-white/10 rounded-xl text-foreground"
                >
                  <option value="google">Miễn phí (Google Translate)</option>
                  <option value="ai">AI chuyên sâu (ChatGPT / Gemini / Gemma)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1">
                  AI Dịch phụ đề (translation_ai_profile_id):
                </label>
                <select
                  value={config.translation_ai_profile_id || ""}
                  onChange={(e) => handleFieldChange("translation_ai_profile_id", e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-black/40 border border-white/10 rounded-xl text-amber-300 font-semibold"
                >
                  {globalProfiles.length > 0 ? (
                    globalProfiles.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.label || p.id} ({p.provider || "openai"} / {p.model || ""})
                      </option>
                    ))
                  ) : (
                    <option value="openai-default">OpenAI Default (gpt-4o-mini)</option>
                  )}
                </select>
                <p className="text-[10px] text-muted-foreground mt-1 font-mono">
                  {selectedTransProfile
                    ? `${selectedTransProfile.provider || 'openai'} • ${selectedTransProfile.model || ''} • ${selectedTransProfile.base_url || ''}`
                    : "Chưa có AI profile khả dụng trong Global Settings."}
                </p>
              </div>
            </div>

            {/* Form Row 2: AI Context Profile & Video Context Description */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1">
                  AI Phân tích Ngữ cảnh (context_ai_profile_id):
                </label>
                <select
                  value={config.context_ai_profile_id || ""}
                  onChange={(e) => handleFieldChange("context_ai_profile_id", e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-black/40 border border-white/10 rounded-xl text-amber-300 font-semibold"
                >
                  {globalProfiles.length > 0 ? (
                    globalProfiles.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.label || p.id} ({p.provider || "openai"} / {p.model || ""})
                      </option>
                    ))
                  ) : (
                    <option value="openai-default">OpenAI Default (gpt-4o-mini)</option>
                  )}
                </select>
                <p className="text-[10px] text-muted-foreground mt-1 font-mono">
                  {selectedContextProfile
                    ? `${selectedContextProfile.provider || 'openai'} • ${selectedContextProfile.model || ''} • ${selectedContextProfile.base_url || ''}`
                    : "Chưa có AI profile khả dụng trong Global Settings."}
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1">
                  Mô tả Ngữ cảnh video (video_context):
                </label>
                <Input
                  type="text"
                  value={config.video_context || "Short fantasy game online videos, MMORPG gameplay review, PvP server war"}
                  onChange={(e) => handleFieldChange("video_context", e.target.value)}
                  placeholder="Short fantasy game online videos, MMORPG gameplay review..."
                />
              </div>
            </div>

            {/* Form Row 3: Source, Target, Tone, Temperature */}
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1 flex items-center gap-1">
                  <Languages className="w-3.5 h-3.5 text-amber-400" /> Ngôn ngữ gốc (source_language):
                </label>
                <Input
                  type="text"
                  value={config.source_language || "Chinese"}
                  onChange={(e) => handleFieldChange("source_language", e.target.value)}
                  placeholder="Chinese, English, Auto..."
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1 flex items-center gap-1">
                  <Globe className="w-3.5 h-3.5 text-amber-400" /> Ngôn ngữ đích (target_language):
                </label>
                <Input
                  type="text"
                  value={config.target_language || "Vietnamese"}
                  onChange={(e) => handleFieldChange("target_language", e.target.value)}
                  placeholder="Vietnamese, English..."
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1">
                  Tone dịch (ai_tone):
                </label>
                <Input
                  type="text"
                  value={config.ai_tone || "natural and fluent"}
                  onChange={(e) => handleFieldChange("ai_tone", e.target.value)}
                  placeholder="natural and fluent"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1 flex items-center gap-1">
                  <Thermometer className="w-3.5 h-3.5 text-amber-400" /> AI Temp (0–2):
                </label>
                <Input
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  value={config.ai_temperature ?? 0.0}
                  onChange={(e) => handleFieldChange("ai_temperature", parseFloat(e.target.value))}
                />
              </div>
            </div>
          </div>
        )}

        {/* Bottom Action Button */}
        <div className="pt-2">
          <Button
            type="button"
            variant="gradient"
            size="lg"
            onClick={handleRunPipeline}
            className="w-full py-4 text-base rounded-2xl font-bold"
          >
            <Play className="w-5 h-5 fill-current mr-2" />
            <span>▶ Chạy Pipeline ngay</span>
          </Button>
        </div>
      </Card>
    </div>
  );
};
