import React, { useState, useEffect, useRef } from "react";
import { toast } from "sonner";
import {
  ArrowLeft,
  Play,
  Film,
  MessageSquare,
  Globe,
  Sparkles,
  CheckCircle,
  CheckCircle2,
  Database,
  Shield,
  Eye,
  Type,
  FolderOpen,
  Wand2,
  Thermometer,
  Languages,
  Volume2,
  Square,
  RefreshCw,
  Cloud,
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
import { Textarea } from "./ui/textarea";
import { Switch } from "./ui/switch";
import { Label } from "./ui/label";
import { Tabs, TabsList, TabsTrigger } from "./ui/tabs";
import { MultiLangTranslateModal } from "./MultiLangTranslateModal";
import { NovelImportModal } from "./NovelImportModal";
import { ScriptReaderEditor } from "./ScriptReaderEditor";
import { ErrorBoundary } from "./ErrorBoundary";

interface ProjectDetailsProps {
  folder: string;
  onBack: () => void;
  onRunSuccess?: () => void;
}

interface NovelSceneItem {
  scene_id: number;
  voiceover: string;
  visual_prompt?: string;
  animation?: string;
  duration?: number;
  audio_file?: string;
}

const extractEpisodeFromPath = (pathStr?: string): number | null => {
  if (!pathStr) return null;
  const clean = pathStr.split(/\r?\n/)[0].trim();
  const m = clean.match(/(?:t[aậ]p|ep|episode)[\s_.-]*(\d+)/i) || clean.match(/(\d+)/);
  if (m && m[1]) {
    const v = parseInt(m[1], 10);
    if (!isNaN(v) && v > 0 && v < 5000) return v;
  }
  return null;
};

export const ProjectDetails: React.FC<ProjectDetailsProps> = ({ folder, onBack, onRunSuccess }) => {
  const [activeTab, setActiveTab] = useState<"video" | "sub" | "translate" | "novel" | "all">("video");
  const [globalProfiles, setGlobalProfiles] = useState<any[]>([]);
  const [translateModalOpen, setTranslateModalOpen] = useState<boolean>(false);
  const [novelModalOpen, setNovelModalOpen] = useState<boolean>(false);
  const [availableNovels, setAvailableNovels] = useState<any[]>([]);
  const [selectedNovel, setSelectedNovel] = useState<any>({
    id: "Pham nhan tu tien",
    name: "Phàm Nhân Tu Tiên",
    chapters_count: 2446
  });

  // Novel Pipeline & Script Text State inside Project
  const [novelCurrentEp, setNovelCurrentEp] = useState<number>(1);
  const [novelNextEp, setNovelNextEp] = useState<number>(2);
  const [novelScriptText, setNovelScriptText] = useState<string>("");
  const [generatingScript, setGeneratingScript] = useState<boolean>(false);
  const [novelScenes, setNovelScenes] = useState<NovelSceneItem[]>([]);
  const [novelLoading, setNovelLoading] = useState<boolean>(false);
  const [novelStepMessage, setNovelStepMessage] = useState<string>("");
  const [novelDraftResult, setNovelDraftResult] = useState<any>(null);
  const [ttsVoices, setTtsVoices] = useState<Record<string, any>>({});
  const [playingVoice, setPlayingVoice] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState<boolean>(false);
  const [syncingDriveVoice, setSyncingDriveVoice] = useState<string | null>(null);
  const audioPreviewRef = useRef<HTMLAudioElement | null>(null);

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

        // Tải danh sách các bộ truyện
        try {
          const nRes = await fetch("/api/novels");
          const nData = await nRes.json();
          if (nData.success && Array.isArray(nData.novels)) {
            setAvailableNovels(nData.novels);
            
            // Ưu tiên chọn truyện: 1. pData.novel_id -> 2. Nhận diện từ video_path -> 3. localStorage -> 4. Truyện đầu tiên
            const initialVideo = pData?.video_path || (pData?.video_paths && pData.video_paths.length > 0 ? pData.video_paths[0] : "");
            const savedLocalStr = localStorage.getItem("capcut_selected_novel");
            let targetNovel = null;
            if (pData?.novel_id) {
              targetNovel = nData.novels.find((n: any) => n.id === pData.novel_id);
            }
            if (!targetNovel && initialVideo) {
              const lowerVid = initialVideo.toLowerCase();
              if (lowerVid.includes("pham nhan") || lowerVid.includes("phàm nhân")) {
                targetNovel = nData.novels.find((n: any) => n.id.toLowerCase().includes("pham") || n.name.toLowerCase().includes("phàm"));
              } else if (lowerVid.includes("xianni") || lowerVid.includes("tiên nghịch") || lowerVid.includes("tien nghich") || lowerVid.includes("仙逆")) {
                targetNovel = nData.novels.find((n: any) => n.id.toLowerCase().includes("xianni") || n.name.toLowerCase().includes("tiên nghịch") || n.name.includes("仙逆"));
              }
            }
            if (!targetNovel && savedLocalStr) {
              try {
                const parsed = JSON.parse(savedLocalStr);
                targetNovel = nData.novels.find((n: any) => n.id === parsed.id) || parsed;
              } catch (_) {}
            }
            if (!targetNovel && nData.novels.length > 0) {
              targetNovel = nData.novels[0];
            }
            if (targetNovel) {
              setSelectedNovel(targetNovel);
            }
          }
        } catch (e) {
          console.error("Lỗi tải danh sách tiểu thuyết:", e);
        }

        // Tải danh mục giọng đọc NghiTTS từ API
        try {
          const vRes = await fetch("/api/tts/voices");
          const vData = await vRes.json();
          if (vData.success && vData.voices) {
            setTtsVoices(vData.voices);
          }
        } catch (e) {
          console.error("Lỗi tải danh mục giọng đọc NghiTTS:", e);
        }

        if (pData?.novel_script_text) {
          setNovelScriptText(pData.novel_script_text);
        }
        const initialVideo = pData?.video_path || (pData?.video_paths && pData.video_paths.length > 0 ? pData.video_paths[0] : "");
        const autoEp = extractEpisodeFromPath(initialVideo);
        if (pData?.novel_current_ep) {
          setNovelCurrentEp(Number(pData.novel_current_ep));
        } else if (autoEp) {
          setNovelCurrentEp(autoEp);
        }
        if (pData?.novel_next_ep) {
          setNovelNextEp(Number(pData.novel_next_ep));
        } else if (autoEp) {
          setNovelNextEp(autoEp + 1);
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

  const [detectedChapterInfo, setDetectedChapterInfo] = useState<any>(null);

  const syncEpisodeFromVideo = (videoPath: string) => {
    const ep = extractEpisodeFromPath(videoPath);
    if (ep) {
      setNovelCurrentEp(ep);
      setNovelNextEp(ep + 1);
      handleFieldChange("novel_current_ep", ep);
      handleFieldChange("novel_next_ep", ep + 1);
    }
  };

  const handleFieldChange = (key: string, value: any) => {
    const updated = { ...config, [key]: value };
    triggerAutoSave(updated);
    if (key === "video_path" && typeof value === "string") {
      syncEpisodeFromVideo(value);
    }
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

  const handleSelectNovel = (novelOrId: any) => {
    let novelObj = typeof novelOrId === "string" 
      ? availableNovels.find((n) => n.id === novelOrId)
      : novelOrId;
    if (!novelObj) return;

    setSelectedNovel(novelObj);
    handleFieldChange("novel_id", novelObj.id);
    handleFieldChange("novel_name", novelObj.name);
    try {
      localStorage.setItem("capcut_selected_novel", JSON.stringify(novelObj));
    } catch (_) {}
    toast.success(`Đã chọn bộ truyện: ${novelObj.name}`, {
      description: "Đã lưu vào cấu hình dự án và tự động nhớ cho các lần mở sau!"
    });
  };

  const handlePlayVoiceSample = async (voiceName: string) => {
    if (audioPreviewRef.current) {
      audioPreviewRef.current.pause();
      if (playingVoice === voiceName) {
        setPlayingVoice(null);
        setPreviewLoading(false);
        return;
      }
    }

    setPlayingVoice(voiceName);
    setPreviewLoading(true);
    try {
      const url = `/api/tts/preview?voice=${encodeURIComponent(voiceName)}`;
      const audio = new Audio(url);
      audioPreviewRef.current = audio;

      audio.oncanplay = () => {
        setPreviewLoading(false);
      };

      audio.onended = () => {
        setPlayingVoice(null);
        setPreviewLoading(false);
      };

      audio.onerror = () => {
        toast.error(`Không thể phát giọng mẫu cho "${voiceName}". Vui lòng thử lại.`);
        setPlayingVoice(null);
        setPreviewLoading(false);
      };

      await audio.play();
    } catch (err) {
      console.error(err);
      toast.error(`Lỗi khi phát âm thanh mẫu: ${err}`);
      setPlayingVoice(null);
      setPreviewLoading(false);
    }
  };

  const handleSyncVoiceToDrive = async (voiceName?: string) => {
    const target = voiceName || config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)";
    setSyncingDriveVoice(target);
    try {
      const res = await fetch("/api/tts/sync_drive", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice: target, download_missing: false })
      });
      const data = await res.json();
      if (data.success) {
        toast.success(`Đã sao lưu giọng "${target}" lên Google Drive!`, {
          description: `Thư mục lưu trữ: ${data.drive_models_dir}`
        });
        // Cập nhật lại danh mục giọng đọc để hiển thị icon Drive
        const vRes = await fetch("/api/tts/voices");
        const vData = await vRes.json();
        if (vData.success && vData.voices) {
          setTtsVoices(vData.voices);
        }
      } else {
        toast.error("Lỗi khi sao lưu giọng lên Drive", { description: data.error });
      }
    } catch (err: any) {
      toast.error("Lỗi kết nối máy chủ sao lưu Drive", { description: err?.message || String(err) });
    } finally {
      setSyncingDriveVoice(null);
    }
  };

  const handleGenerateScriptText = async () => {
    const videoSource = config.video_path?.trim();
    if (!videoSource) {
      toast.error("Chưa có video ở Step 1–2!", {
        description: "Vui lòng nhập hoặc bấm '📂 Chọn file' tại tab 'Step 1-2: Video đầu vào' làm nguồn tham khảo."
      });
      setActiveTab("video");
      return;
    }

    setGeneratingScript(true);
    toast.info("Đang đối chiếu lời thoại tham khảo & sinh kịch bản AI...", {
      description: `Áp dụng chỉ đạo từ Prompt & kho chương ${selectedNovel?.name || "nguyên tác"}`
    });
    try {
      const res = await fetch("/api/novel/generate_script_text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          novel_id: selectedNovel?.id || "Pham nhan tu tien",
          current_episode_num: novelCurrentEp,
          next_episode_num: novelNextEp,
          video_path: videoSource,
          transcript_text: "",
          prompt: config.novel_prompt || ""
        })
      });
      const data = await res.json();
      if (data.success && data.full_plain_text) {
        setNovelScriptText(data.full_plain_text);
        handleFieldChange("novel_script_text", data.full_plain_text);
        if (data.detected_info) {
          setDetectedChapterInfo(data.detected_info);
        }
        toast.success(`🎉 Đã sinh Kịch bản AI (.txt) thành công!`, {
          description: data.detected_info?.detected_end_chapter 
            ? `Khớp nội dung Chương ${data.detected_info.detected_end_chapter}. Đã biên kịch tiếp Chương ${data.detected_info.next_episode_chapters?.join(', ')}`
            : `${data.scenes_count || 20} phân cảnh • Sẵn sàng chỉnh sửa.`
        });
      } else {
        toast.error("Không thể tạo kịch bản", { description: data.error || "Lỗi server" });
      }
    } catch (err: any) {
      toast.error("Lỗi kết nối", { description: err.message });
    } finally {
      setGeneratingScript(false);
    }
  };

  const handleRunNovelPipeline = async () => {
    setNovelLoading(true);
    setNovelStepMessage("B1: Đang sinh âm thanh NghiTTS 1.2x...");
    toast.info("Đang chạy Quy trình 5 Bước Sản Xuất Video Tiểu Thuyết...", {
      description: "B1: NghiTTS 1.2x ➔ B2: Xếp Audio & SRT ➔ B3: AI Phân Cảnh ➔ B4: CapCut Draft ➔ B5: Mở CapCut PC"
    });

    try {
      const chosenVoice = config.novel_tts_voice || "Ngọc Huyền (mới)";
      const chosenSpeed = config.novel_tts_speed ?? 1.2;
      const mediaList = (config.video_paths && config.video_paths.length > 0)
        ? config.video_paths
        : [config.video_path].filter(Boolean);

      const res = await fetch("/api/novel/pipeline/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current_episode: novelCurrentEp,
          novel_id: selectedNovel?.id || "Pham nhan tu tien",
          prompt: config.novel_prompt,
          voice: chosenVoice,
          tts_speed: chosenSpeed,
          canvas_ratio: config.canvas_ratio || "16:9",
          script_text: config.novel_script_text || novelScriptText,
          scenes: novelScenes,
          media_paths: mediaList,
          auto_open_capcut: config.auto_open_capcut ?? true
        })
      });
      const data = await res.json();
      if (data.success) {
        setNovelDraftResult(data);
        if (data.scenes) setNovelScenes(data.scenes);
        toast.success(`🎉 Đã sản xuất xong CapCut Draft hoàn chỉnh!`, {
          description: `${data.sentences_count || 0} câu • ${data.scenes_count || 0} phân cảnh • ${Math.round(data.total_duration_sec || 0)}s audio • Đã mở CapCut PC!`
        });
      } else {
        toast.error("Lỗi khi chạy pipeline tiểu thuyết", { description: data.error });
      }
    } catch (e: any) {
      toast.error("Lỗi kết nối", { description: e.message });
    } finally {
      setNovelLoading(false);
      setNovelStepMessage("");
    }
  };

  const handleOpenCapCut = async () => {
    try {
      toast.info("Đang kích hoạt mở CapCut PC...");
      const res = await fetch("/api/novel/open_capcut", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ draft_folder: novelDraftResult?.draft_folder || "" })
      });
      const data = await res.json();
      if (data.success) {
        toast.success("CapCut PC đã mở sẵn sàng!", {
          description: "Mở CapCut, bấm vào Dự án ở đầu trang chủ và bấm 'Export' để xuất video MP4."
        });
      } else {
        toast.error("Không thể mở CapCut tự động", { description: data.error });
      }
    } catch (e: any) {
      toast.error("Lỗi mở CapCut", { description: e.message });
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

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={() => setTranslateModalOpen(true)}
            className="bg-gradient-to-r from-amber-500 via-purple-600 to-[#622FF6] hover:opacity-90 text-white font-bold text-xs h-8 gap-1.5 shadow-md shadow-purple-500/20"
          >
            <Languages className="w-3.5 h-3.5" />
            🌐 Dịch Đa Ngôn Ngữ
          </Button>

          <Button
            size="sm"
            onClick={handleRunNovelPipeline}
            disabled={novelLoading}
            className="bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-600 hover:to-orange-700 text-zinc-950 font-bold text-xs h-8 gap-1.5 shadow-md shadow-amber-500/20"
          >
            <Sparkles className="w-3.5 h-3.5 fill-current text-zinc-950" />
            {novelLoading ? "Đang xử lý..." : "📖 Chạy Tiểu Thuyết AI"}
          </Button>

          <Button
            size="sm"
            onClick={handleRunPipeline}
            className="bg-cyan-500 hover:bg-cyan-600 text-black font-bold text-xs h-8 gap-1.5"
          >
            <Play className="w-3.5 h-3.5 fill-black" />
            Khởi chạy Pipeline
          </Button>
        </div>
      </Card>

      {/* Tabs Bar - Shadcn Tabs */}
      <Tabs value={activeTab} onValueChange={(val) => setActiveTab(val as any)} className="w-full">
        <TabsList className="w-full justify-start h-11 p-1 bg-black/40 border border-white/10 rounded-xl overflow-x-auto gap-1">
          <TabsTrigger value="video" className="text-xs data-[state=active]:bg-cyan-500/20 data-[state=active]:text-cyan-300">
            <Film className="w-3.5 h-3.5 mr-1.5" /> 🎬 Video & Xử lý (Step 1–2)
          </TabsTrigger>
          <TabsTrigger value="sub" className="text-xs data-[state=active]:bg-purple-500/20 data-[state=active]:text-purple-300">
            <MessageSquare className="w-3.5 h-3.5 mr-1.5" /> 📝 Phụ đề & Whisper (Step 3, 5–7)
          </TabsTrigger>
          <TabsTrigger value="translate" className="text-xs data-[state=active]:bg-blue-500/20 data-[state=active]:text-blue-300">
            <Globe className="w-3.5 h-3.5 mr-1.5" /> 🌐 Dịch thuật & AI (Step 4)
          </TabsTrigger>
          <TabsTrigger value="novel" className="text-xs data-[state=active]:bg-amber-500/20 data-[state=active]:text-amber-300">
            <Sparkles className="w-3.5 h-3.5 mr-1.5 text-amber-400" /> 📖 Thuyết Minh Tiểu Thuyết (Novel AI)
          </TabsTrigger>
          <TabsTrigger value="all" className="text-xs data-[state=active]:bg-zinc-700/40 data-[state=active]:text-zinc-200">
            <Sparkles className="w-3.5 h-3.5 mr-1.5" /> ⚡ Tất cả cài đặt
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {/* Form Content */}
      <Card className="p-6 space-y-8">
        {(activeTab === "video" || activeTab === "all") && (
          <div className="space-y-4 pb-6 border-b border-white/10">
            <h3 className="text-sm font-bold text-cyan-400 flex items-center gap-2">
              <Film className="w-4 h-4" /> Step 1-2: Video đầu vào & Canvas Ratio
            </h3>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <Label className="text-xs font-semibold text-muted-foreground">
                  Danh sách file Video (đường dẫn tuyệt đối từng dòng):
                </Label>
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
              <Textarea
                rows={3}
                value={config.video_path || ""}
                onChange={(e) => handleFieldChange("video_path", e.target.value)}
                placeholder="C:\Videos\sample1.mp4&#10;C:\Videos\sample2.mp4"
                className="w-full px-3 py-2 text-xs bg-black/40 border border-white/10 rounded-xl text-foreground font-mono focus:outline-none focus:border-cyan-400 min-h-[75px]"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <Label className="block text-xs font-semibold text-muted-foreground mb-1">
                  Tốc độ Video:
                </Label>
                <Input
                  type="number"
                  step="0.01"
                  value={config.speed ?? 0.77}
                  onChange={(e) => handleFieldChange("speed", parseFloat(e.target.value))}
                />
              </div>
              <div>
                <Label className="block text-xs font-semibold text-muted-foreground mb-1">
                  Khung hình (Canvas Aspect Ratio):
                </Label>
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
              <div className="flex items-center space-x-2.5">
                <Switch
                  id="enable_anti_copyright"
                  checked={config.enable_anti_copyright ?? true}
                  onCheckedChange={(checked) => handleFieldChange("enable_anti_copyright", checked)}
                  className="data-[state=checked]:bg-cyan-600"
                />
                <Label htmlFor="enable_anti_copyright" className="flex items-center gap-1.5 cursor-pointer text-xs font-medium text-zinc-200">
                  <Shield className="w-3.5 h-3.5 text-cyan-400" /> Lách bản quyền động (Smart Defense)
                </Label>
              </div>

              <div className="flex items-center space-x-2.5">
                <Switch
                  id="mirror_video"
                  checked={config.mirror_video ?? false}
                  onCheckedChange={(checked) => handleFieldChange("mirror_video", checked)}
                  className="data-[state=checked]:bg-cyan-600"
                />
                <Label htmlFor="mirror_video" className="cursor-pointer text-xs font-medium text-zinc-200">
                  🪞 Mirror Video (Lật ngang)
                </Label>
              </div>

              <div className="flex items-center space-x-2.5">
                <Switch
                  id="hardsub_blur_enabled"
                  checked={config.hardsub_blur_enabled ?? true}
                  onCheckedChange={(checked) => handleFieldChange("hardsub_blur_enabled", checked)}
                  className="data-[state=checked]:bg-purple-600"
                />
                <Label htmlFor="hardsub_blur_enabled" className="flex items-center gap-1.5 cursor-pointer text-xs font-medium text-zinc-200">
                  <Eye className="w-3.5 h-3.5 text-purple-400" /> Làm mờ Hardsub
                </Label>
              </div>

              <div className="flex items-center space-x-2.5">
                <Switch
                  id="filter_audio"
                  checked={config.filter_audio ?? false}
                  onCheckedChange={(checked) => handleFieldChange("filter_audio", checked)}
                  className="data-[state=checked]:bg-emerald-600"
                />
                <Label htmlFor="filter_audio" className="flex items-center gap-1.5 cursor-pointer text-xs font-medium text-zinc-200">
                  <Wand2 className="w-3.5 h-3.5 text-emerald-400" /> 🧹 Lọc âm gốc (Demucs + DeepFilter)
                </Label>
              </div>
            </div>
          </div>
        )}

        {(activeTab === "sub" || activeTab === "all") && (
          <div className="space-y-4 pb-6 border-b border-white/10">
            <h3 className="text-sm font-bold text-purple-400 flex items-center gap-2">
              <MessageSquare className="w-4 h-4" /> Step 3, 5-7: Phụ đề, Whisper GPU & Giọng đọc TTS
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Cột 1: Model Whisper & Tự động mở CapCut */}
              <div className="space-y-3">
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

                <div className="pt-1">
                  <div className="flex items-center space-x-2.5">
                    <Switch
                      id="auto_open_capcut"
                      checked={config.auto_open_capcut ?? true}
                      onCheckedChange={(checked) => handleFieldChange("auto_open_capcut", checked)}
                      className="data-[state=checked]:bg-emerald-600"
                    />
                    <Label htmlFor="auto_open_capcut" className="cursor-pointer text-xs font-medium text-emerald-400">
                      Khởi chạy CapCut PC ngay sau khi tạo Draft
                    </Label>
                  </div>
                </div>
              </div>

              {/* Cột 2: Cấu hình TTS & Giọng đọc NghiTTS Động */}
              <div className="space-y-3 p-3.5 rounded-xl bg-purple-950/20 border border-purple-500/30">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <Label className="block text-xs font-semibold text-muted-foreground mb-1">
                      Engine TTS:
                    </Label>
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
                    <Label className="block text-xs font-semibold text-muted-foreground mb-1">
                      Tốc độ đọc (TTS Speed):
                    </Label>
                    <div className="flex items-center gap-2">
                      <Input
                        type="number"
                        step="0.05"
                        min="0.5"
                        max="2.5"
                        value={config.novel_tts_speed ?? config.tts_speed ?? 1.2}
                        onChange={(e) => {
                          const val = parseFloat(e.target.value);
                          handleFieldChange("tts_speed", val);
                          handleFieldChange("novel_tts_speed", val);
                        }}
                        className="h-8 text-xs font-bold font-mono bg-black/40 border-purple-500/30 text-amber-300"
                      />
                      <Badge className="bg-purple-500/20 text-purple-300 border-purple-500/40 text-[11px] shrink-0 font-mono">
                        {config.novel_tts_speed ?? config.tts_speed ?? 1.2}x
                      </Badge>
                    </div>
                  </div>
                </div>

                {/* Giọng đọc NghiTTS nạp động từ API + Nút nghe thử mẫu */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label className="block text-xs font-semibold text-purple-300 flex items-center gap-1.5">
                      <Volume2 className="w-3.5 h-3.5 text-amber-400" />
                      Giọng Đọc NghiTTS (17 Giọng Đọc):
                    </Label>
                    <div className="flex items-center gap-2">
                      {Object.keys(ttsVoices).length > 0 && (
                        <span className="text-[10px] text-emerald-400 font-mono">
                          ✓ {Object.keys(ttsVoices).length} giọng
                        </span>
                      )}
                      {/* Trạng thái Google Drive & Nút sao lưu lên Drive */}
                      {ttsVoices[config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)"]?.is_in_drive ? (
                        <Badge variant="outline" className="h-6 px-2 text-[10px] bg-emerald-950/40 text-emerald-300 border-emerald-500/40 gap-1 font-medium" title="Model và âm thanh mẫu đã được đồng bộ an toàn trên Google Drive">
                          <Cloud className="w-3 h-3 text-emerald-400" />
                          <span>Drive ✓</span>
                        </Badge>
                      ) : (
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={syncingDriveVoice !== null}
                          onClick={() => handleSyncVoiceToDrive(config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)")}
                          className="h-6 px-2 text-[11px] gap-1 rounded-lg bg-blue-950/40 text-blue-200 border-blue-500/40 hover:bg-blue-900/50 transition-all"
                          title="Lưu model giọng đọc (.onnx) và âm thanh mẫu (.wav) lên thư mục Google Drive (G:\My Drive\CapCutRecapAI\tts_models)"
                        >
                          {syncingDriveVoice === (config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)") ? (
                            <>
                              <RefreshCw className="w-3 h-3 animate-spin text-blue-300" />
                              <span>Đang lưu...</span>
                            </>
                          ) : (
                            <>
                              <Cloud className="w-3 h-3 text-blue-400" />
                              <span>☁️ Lưu Drive</span>
                            </>
                          )}
                        </Button>
                      )}
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => handlePlayVoiceSample(config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)")}
                        className={`h-6 px-2.5 text-[11px] gap-1.5 rounded-lg border transition-all ${
                          playingVoice === (config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)")
                            ? "bg-amber-500 text-zinc-950 border-amber-400 font-bold"
                            : "bg-purple-950/40 text-purple-200 border-purple-500/40 hover:bg-purple-900/50"
                        }`}
                      >
                        {previewLoading && playingVoice === (config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)") ? (
                          <>
                            <RefreshCw className="w-3 h-3 animate-spin text-zinc-950" />
                            <span>Đang tải...</span>
                          </>
                        ) : playingVoice === (config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)") ? (
                          <>
                            <Square className="w-3 h-3 fill-current" />
                            <span>Dừng nghe</span>
                          </>
                        ) : (
                          <>
                            <Volume2 className="w-3 h-3 text-amber-400" />
                            <span>🔊 Nghe thử giọng</span>
                          </>
                        )}
                      </Button>
                    </div>
                  </div>

                  <select
                    value={config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)"}
                    onChange={(e) => {
                      handleFieldChange("novel_tts_voice", e.target.value);
                      handleFieldChange("tts_voice", e.target.value);
                    }}
                    className="w-full px-3 py-2 text-xs bg-black/60 border border-purple-500/40 rounded-xl text-amber-300 font-medium outline-none focus:border-purple-400"
                  >
                    {Object.keys(ttsVoices).length > 0 ? (
                      Object.entries(ttsVoices).map(([vName, vMeta]: [string, any]) => (
                        <option key={vName} value={vName}>
                          🎙️ {vName} {vMeta.is_in_drive ? "☁️ [Drive]" : ""} - [{vMeta.region} {vMeta.gender === "female" ? "Nữ" : "Nam"}] - {vMeta.style}
                        </option>
                      ))
                    ) : (
                      <>
                        <option value="Ngọc Huyền (mới)">🎙️ Ngọc Huyền (mới) ☁️ [Drive] - [Bắc Nữ] - Đọc truyện kiếm hiệp, truyền cảm</option>
                        <option value="Duy Oryx">🎙️ Duy Oryx ☁️ [Drive] - [Bắc Nam] - Trầm ấm, đĩnh đạc, hiện đại</option>
                        <option value="Mạnh Dũng">🎙️ Mạnh Dũng ☁️ [Drive] - [Bắc Nam] - Hào hùng, khí thế, chiến đấu</option>
                        <option value="Thảo Chi">🎙️ Thảo Chi - [Bắc Nữ] - Ngọt ngào, nhẹ nhàng</option>
                        <option value="Minh Khang">🎙️ Minh Khang - [Nam Nam] - Trẻ trung, tự nhiên, gần gũi</option>
                        <option value="Mỹ Tâm">🎙️ Mỹ Tâm - [Trung Nữ] - Giọng miền Trung chân chất, cảm xúc</option>
                      </>
                    )}
                  </select>

                  {/* Hiển thị câu thoại mẫu đặc trưng của giọng đang chọn */}
                  {ttsVoices[config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)"] && (
                    <div className="p-2.5 rounded-lg bg-black/50 border border-purple-500/30 text-[11px] space-y-1">
                      <div className="text-zinc-400 flex items-center justify-between">
                        <span>Phong cách: <strong className="text-zinc-200">{ttsVoices[config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)"].style}</strong></span>
                        <span className="font-mono text-purple-300">
                          [{ttsVoices[config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)"].region} • {ttsVoices[config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)"].gender === "female" ? "Nữ" : "Nam"}]
                        </span>
                      </div>
                      {ttsVoices[config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)"].sample_quote && (
                        <div className="text-amber-300 italic flex items-start gap-1.5 pt-0.5 border-t border-purple-500/20">
                          <span className="shrink-0 text-amber-400">💬</span>
                          <span>"{ttsVoices[config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)"].sample_quote}"</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Subtitle Font Customization - Col-2 Grid */}
            <div className="p-4 rounded-xl bg-black/30 border border-white/10 space-y-3">
              <h4 className="text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                <Type className="w-3.5 h-3.5" /> Định dạng phông chữ Phụ đề (Subtitle Style)
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label className="block text-[11px] font-medium text-muted-foreground mb-1">Font chữ (Đường dẫn absolute):</Label>
                  <Input
                    type="text"
                    value={config.font_name || "C:/Users/nguye/AppData/Local/CapCut/Apps/8.9.1.3802/Resources/Font/SystemFont/en.ttf"}
                    onChange={(e) => handleFieldChange("font_name", e.target.value)}
                    className="font-mono text-xs"
                  />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <Label className="block text-[11px] font-medium text-muted-foreground mb-1">Cỡ chữ Sub (font_size):</Label>
                    <Input
                      type="number"
                      step="0.5"
                      value={config.font_size ?? 15.0}
                      onChange={(e) => handleFieldChange("font_size", parseFloat(e.target.value))}
                    />
                  </div>
                  <div>
                    <Label className="block text-[11px] font-medium text-muted-foreground mb-1">Màu chữ (font_color):</Label>
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
            </div>

            <div className="flex flex-wrap items-center gap-6 pt-2">
              <div className="flex items-center space-x-2.5">
                <Switch
                  id="use_local_whisper"
                  checked={config.use_local_whisper ?? true}
                  onCheckedChange={(checked) => handleFieldChange("use_local_whisper", checked)}
                  className="data-[state=checked]:bg-purple-600"
                />
                <Label htmlFor="use_local_whisper" className="cursor-pointer text-xs font-medium text-zinc-200">
                  Whisper GPU (Local GPU khuyên dùng)
                </Label>
              </div>

              <div className="flex items-center space-x-2.5">
                <Switch
                  id="use_local_ocr"
                  checked={config.use_local_ocr ?? false}
                  onCheckedChange={(checked) => handleFieldChange("use_local_ocr", checked)}
                  className="data-[state=checked]:bg-purple-600"
                />
                <Label htmlFor="use_local_ocr" className="cursor-pointer text-xs font-medium text-zinc-200">
                  PaddleOCR (Quét chữ từ frame)
                </Label>
              </div>

              <div className="flex items-center space-x-2.5">
                <Switch
                  id="whisper_vad_filter"
                  checked={config.whisper_vad_filter ?? true}
                  onCheckedChange={(checked) => handleFieldChange("whisper_vad_filter", checked)}
                  className="data-[state=checked]:bg-purple-600"
                />
                <Label htmlFor="whisper_vad_filter" className="cursor-pointer text-xs font-medium text-zinc-200">
                  VAD Filter (Lọc ảo giác)
                </Label>
              </div>
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
                <Label className="block text-xs font-semibold text-muted-foreground mb-1">
                  Nguồn dịch (translation_method):
                </Label>
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
                <Label className="block text-xs font-semibold text-muted-foreground mb-1">
                  AI Dịch phụ đề (translation_ai_profile_id):
                </Label>
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
                <Label className="block text-xs font-semibold text-muted-foreground mb-1">
                  AI Phân tích Ngữ cảnh (context_ai_profile_id):
                </Label>
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
                <Label className="block text-xs font-semibold text-muted-foreground mb-1">
                  Mô tả Ngữ cảnh video (video_context):
                </Label>
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
                <Label className="block text-xs font-semibold text-muted-foreground mb-1 flex items-center gap-1">
                  <Languages className="w-3.5 h-3.5 text-amber-400" /> Ngôn ngữ gốc (source_language):
                </Label>
                <Input
                  type="text"
                  value={config.source_language || "Chinese"}
                  onChange={(e) => handleFieldChange("source_language", e.target.value)}
                  placeholder="Chinese, English, Auto..."
                />
              </div>

              <div>
                <Label className="block text-xs font-semibold text-muted-foreground mb-1 flex items-center gap-1">
                  <Globe className="w-3.5 h-3.5 text-amber-400" /> Ngôn ngữ đích (target_language):
                </Label>
                <Input
                  type="text"
                  value={config.target_language || "Vietnamese"}
                  onChange={(e) => handleFieldChange("target_language", e.target.value)}
                  placeholder="Vietnamese, English..."
                />
              </div>

              <div>
                <Label className="block text-xs font-semibold text-muted-foreground mb-1">
                  Tone dịch (ai_tone):
                </Label>
                <Input
                  type="text"
                  value={config.ai_tone || "natural and fluent"}
                  onChange={(e) => handleFieldChange("ai_tone", e.target.value)}
                  placeholder="natural and fluent"
                />
              </div>

              <div>
                <Label className="block text-xs font-semibold text-muted-foreground mb-1 flex items-center gap-1">
                  <Thermometer className="w-3.5 h-3.5 text-amber-400" /> AI Temp (0–2):
                </Label>
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

        {/* Tab 4: Novel Recap (Tiểu Thuyết AI) */}
        {(activeTab === "novel" || activeTab === "all") && (
          <ErrorBoundary fallbackTitle="Lỗi hiển thị Tab Thuyết Minh Tiểu Thuyết">
            <div className="space-y-4 pb-6 border-b border-white/10">
            {/* Header & Novel Selector */}
            <div className="p-4 rounded-xl bg-gradient-to-r from-amber-500/15 via-zinc-900/60 to-zinc-900/40 border border-amber-500/30 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Sparkles className="w-4 h-4 text-amber-400" />
                  <h3 className="text-sm font-bold text-white">
                    Bộ Truyện:
                  </h3>
                  {/* Novel Selector Dropdown */}
                  <select
                    value={selectedNovel?.id || "Pham nhan tu tien"}
                    onChange={(e) => handleSelectNovel(e.target.value)}
                    className="h-8 px-3 rounded-lg bg-zinc-900/90 border border-amber-500/40 text-xs font-semibold text-amber-300 outline-none focus:border-amber-400"
                  >
                    {availableNovels && availableNovels.length > 0 ? (
                      availableNovels.map((n: any) => (
                        <option key={n.id} value={n.id} className="bg-zinc-900 text-zinc-100">
                          {n.name} ({n.chapters_count?.toLocaleString() || 0} chương)
                        </option>
                      ))
                    ) : (
                      <option value={selectedNovel?.id || "Pham nhan tu tien"} className="bg-zinc-900 text-zinc-100">
                        {selectedNovel?.name || "Phàm Nhân Tu Tiên"} ({selectedNovel?.chapters_count?.toLocaleString() || 0} chương)
                      </option>
                    )}
                  </select>

                  <Badge className="bg-amber-500/20 text-amber-300 border-amber-500/30 text-[10px] font-mono">
                    {selectedNovel?.chapters_count?.toLocaleString() || 0} Chương
                  </Badge>
                </div>
                <p className="text-xs text-zinc-400">
                  Tự động lưu bộ truyện vào cấu hình folder này để lần sau không cần chọn lại truyện.
                </p>
              </div>

              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setNovelModalOpen(true)}
                  className="border-amber-500/40 bg-zinc-900/80 hover:bg-amber-500/20 text-amber-300 text-xs h-8 gap-1.5 rounded-xl shrink-0"
                >
                  <FolderOpen className="w-3.5 h-3.5" />
                  📚 Quản Lý & Nhập Truyện Mới
                </Button>
              </div>
            </div>

            {/* NGUỒN VIDEO/SRT THAM KHẢO (TỰ ĐỘNG TỪ STEP 1–2) */}
            <div className="p-4 rounded-xl bg-zinc-900/70 border border-zinc-800/90 space-y-2.5 shadow-sm">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <label className="text-xs font-bold text-zinc-100 flex items-center gap-2">
                  <Database className="w-4 h-4 text-amber-400" />
                  Nguồn Video/SRT Tham Khảo (Dùng Video Tại Step 1–2):
                </label>
                
                {config.video_path?.trim() ? (
                  <Badge variant="outline" className="text-[11px] border-emerald-500/40 text-emerald-400 bg-emerald-950/20 font-medium">
                    ✓ Đã lấy từ Step 1–2
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-[11px] border-amber-500/40 text-amber-400 bg-amber-950/20 font-medium">
                    ⚠️ Chưa có video tại Step 1–2
                  </Badge>
                )}
              </div>

              {/* Hiển thị video đang dùng từ Step 1-2 */}
              <div className="p-3 rounded-lg bg-black/50 border border-zinc-800 font-mono text-xs text-zinc-300 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 overflow-hidden">
                  <Film className="w-4 h-4 text-cyan-400 shrink-0" />
                  <div className="truncate">
                    {config.video_path?.trim() ? (
                      <span className="text-zinc-200">{config.video_path.split(/\r?\n/)[0]}</span>
                    ) : (
                      <span className="text-zinc-500 italic">Chưa chọn video ở Step 1–2. (Video/SRT là nguồn dữ liệu tham khảo đối chiếu).</span>
                    )}
                  </div>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setActiveTab("video")}
                  className="h-6 px-2 text-[11px] text-cyan-400 hover:text-cyan-300 hover:bg-cyan-950/40 shrink-0"
                >
                  Đổi Video tại Step 1–2 ➔
                </Button>
              </div>

              <p className="text-[11px] text-zinc-400 italic">
                💡 Video/SRT chỉ đóng vai trò là nguồn dữ liệu tham khảo (lời thoại, nhân vật, bối cảnh). Mọi yêu cầu viết kịch bản, nối tiếp tập trước hay phân tích trailer đều được chỉ đạo linh hoạt qua <strong>Prompt</strong>.
              </p>
            </div>

            {/* AI Direction Prompt (Động hoàn toàn qua Prompt) */}
            <div className="p-4 rounded-xl bg-zinc-900/60 border border-zinc-800 space-y-3 shadow-sm">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <label className="text-xs font-bold text-zinc-100 flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-amber-400" />
                  Prompt Chỉ Đạo AI & Yêu Cầu Kịch Bản (Số tập, cốt truyện, phong cách review...):
                </label>
                <Badge variant="outline" className="text-[10px] text-amber-400 border-amber-500/30 bg-amber-950/20 font-mono">
                  ⚡ Điều Khiển Động Qua Prompt
                </Badge>
              </div>

              {/* Gợi ý mẫu prompt nhanh */}
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => handleFieldChange("novel_prompt", "Viết tiếp tập mới nối tiếp ngay sau đoạn kết của video tham khảo. Phân tích diễn biến các chương tiếp theo kịch tính, bám sát nguyên tác.")}
                  className="text-xs px-2.5 py-1 rounded-lg bg-zinc-800/80 text-zinc-300 hover:bg-amber-500/20 hover:text-amber-300 hover:border-amber-500/40 border border-zinc-700/60 transition-colors"
                >
                  🎬 Viết tiếp đoạn kết
                </button>
                <button
                  type="button"
                  onClick={() => handleFieldChange("novel_prompt", "Phân tích các tình tiết xuất hiện trong trailer video tham khảo để spoiler chi tiết nội dung tập sắp chiếu.")}
                  className="text-xs px-2.5 py-1 rounded-lg bg-zinc-800/80 text-zinc-300 hover:bg-amber-500/20 hover:text-amber-300 hover:border-amber-500/40 border border-zinc-700/60 transition-colors"
                >
                  🔥 Spoiler theo Trailer
                </button>
                <button
                  type="button"
                  onClick={() => handleFieldChange("novel_prompt", "Tập trung vào đại chiến đỉnh điểm của tập mới, miêu tả chi tiết các chiêu thức thần thông, bảo vật và diễn biến giao tranh ác liệt.")}
                  className="text-xs px-2.5 py-1 rounded-lg bg-zinc-800/80 text-zinc-300 hover:bg-amber-500/20 hover:text-amber-300 hover:border-amber-500/40 border border-zinc-700/60 transition-colors"
                >
                  ⚔️ Tập trung đại chiến
                </button>
                <button
                  type="button"
                  onClick={() => handleFieldChange("novel_prompt", "Tóm tắt review nhanh toàn bộ diễn biến các chương liên quan, văn phong lôi cuốn dí dỏm chuẩn YouTuber review anime.")}
                  className="text-xs px-2.5 py-1 rounded-lg bg-zinc-800/80 text-zinc-300 hover:bg-amber-500/20 hover:text-amber-300 hover:border-amber-500/40 border border-zinc-700/60 transition-colors"
                >
                  🎙️ Review dí dỏm cuốn hút
                </button>
              </div>

              <Textarea
                value={config.novel_prompt || ""}
                onChange={(e) => handleFieldChange("novel_prompt", e.target.value)}
                rows={3}
                className="w-full p-3 rounded-lg bg-zinc-950/80 border border-zinc-800 text-xs text-zinc-200 leading-relaxed outline-none focus:border-amber-400 resize-none font-sans min-h-[75px]"
                placeholder="Nhập yêu cầu kịch bản... Ví dụ: 'Viết tiếp tập 190 nối tiếp kết thúc video tập 189', hoặc: 'Dựa vào trailer tập 190 để spoiler tình tiết Hàn Lập đại chiến ma nhân...', hoặc: 'Chỉ định viết từ chương 809 đến chương 810...'"
              />
              <p className="text-[11px] text-zinc-400 italic">
                💡 Không cần chọn mốc tập cố định: Bạn có thể nhập bất kỳ số tập nào (ví dụ: Tập 190, Tập 191...) hoặc yêu cầu cụ thể ngay trong Prompt trên, AI sẽ tự động phân tích và xử lý.
              </p>
            </div>

            {/* Detected Chapter Notification Card */}
            {detectedChapterInfo && (detectedChapterInfo.detected_end_chapter || detectedChapterInfo.next_episode_chapters) && (
              <div className="p-3 rounded-xl bg-amber-950/30 border border-amber-500/40 text-xs space-y-1.5">
                <div className="flex items-center gap-2 text-amber-400 font-semibold">
                  <CheckCircle className="w-4 h-4 text-emerald-400" />
                  <span>🎯 Kết quả đối chiếu Lời thoại Video/SRT: Khớp nội dung Chương {detectedChapterInfo.detected_end_chapter}</span>
                </div>
                {detectedChapterInfo.detected_chapter_title && (
                  <div className="text-zinc-300 font-mono text-[11px] pl-6">
                    Tiêu đề nguyên tác: <strong>{detectedChapterInfo.detected_chapter_title}</strong>
                  </div>
                )}
                {detectedChapterInfo.coverage_timeline && (
                  <div className="mx-6 p-2 rounded-lg bg-emerald-950/50 border border-emerald-500/40 text-emerald-300 font-mono text-[11px] flex items-center gap-2">
                    <span className="text-emerald-400 font-bold">📍 Trích xuất (% từng chương):</span>
                    <span>{detectedChapterInfo.coverage_timeline}</span>
                  </div>
                )}
                {detectedChapterInfo.start_cut_point && (
                  <div className="text-zinc-300 text-[11px] pl-6 flex items-center gap-1.5">
                    <span className="inline-block w-2 h-2 rounded-full bg-emerald-400"></span>
                    <span><strong>Điểm bắt đầu:</strong> {detectedChapterInfo.start_cut_point}</span>
                  </div>
                )}
                {detectedChapterInfo.end_cut_point && (
                  <div className="text-pink-300 text-[11px] pl-6 flex items-center gap-1.5">
                    <span className="inline-block w-2 h-2 rounded-full bg-pink-400"></span>
                    <span><strong>Điểm ngắt Cliffhanger:</strong> {detectedChapterInfo.end_cut_point}</span>
                  </div>
                )}
                {detectedChapterInfo.next_episode_chapters && (
                  <div className="text-emerald-400 font-mono text-[11px] pl-6">
                    ➡️ Danh sách chương nạp vào AI: <strong>Chương {detectedChapterInfo.next_episode_chapters.join(", ")}</strong>
                  </div>
                )}
                {detectedChapterInfo.ending_summary && (
                  <div className="text-zinc-400 text-[11px] pl-6">
                    Tóm tắt bối cảnh: {detectedChapterInfo.ending_summary}
                  </div>
                )}
                {detectedChapterInfo.pacing_assessment && (
                  <div className="text-cyan-400 font-mono text-[11px] pl-6">
                    ⚡ Phân tích nhịp độ: {detectedChapterInfo.pacing_assessment}
                  </div>
                )}
                {detectedChapterInfo.bridge_summary && (
                  <div className="text-amber-300/90 text-[11px] pl-6 pt-1 border-t border-amber-500/20 italic">
                    🌉 Cầu nối tóm tắt tập trung gian: {detectedChapterInfo.bridge_summary}
                  </div>
                )}
              </div>
            )}

            {/* UPGRADED SCRIPT READER & INTERACTIVE EDITOR (VỪA ĐỌC VỪA SỬA) */}
            <ScriptReaderEditor
              value={config.novel_script_text || novelScriptText}
              onChange={(val) => {
                setNovelScriptText(val);
                handleFieldChange("novel_script_text", val);
              }}
              onGenerateAI={handleGenerateScriptText}
              generating={generatingScript}
              novelTitle={selectedNovel?.name || "Phàm Nhân Tu Tiên"}
              onClear={() => {
                setNovelScriptText("");
                handleFieldChange("novel_script_text", "");
                toast.info("Đã làm trống khung kịch bản");
              }}
              ttsSpeed={config.novel_tts_speed ? parseFloat(config.novel_tts_speed) : 1.2}
            />
              {/* THANH ĐIỀU KHIỂN & KÍCH HOẠT NHANH SẢN XUẤT CAPCUT - SHADCN UI */}
              <Card className="p-3.5 bg-zinc-900/90 border-amber-500/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs shadow-md">
                <div className="flex flex-wrap items-center gap-2 text-zinc-300">
                  <Sparkles className="w-4 h-4 text-amber-400 shrink-0" />
                  <span className="flex items-center gap-1.5 flex-wrap">
                    Giọng đọc:
                    <Badge variant="outline" className="text-amber-300 border-amber-500/40 bg-amber-950/20 font-semibold text-xs py-0.5 px-2">
                      {config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)"}
                    </Badge>
                    {ttsVoices[config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)"]?.is_in_drive ? (
                      <span className="text-[10px] text-emerald-400 flex items-center gap-0.5 px-1 py-0.5 rounded bg-emerald-950/30 border border-emerald-500/30" title="Model giọng đọc đã được sao lưu an toàn trên Google Drive">
                        <Cloud className="w-3 h-3 text-emerald-400" />
                        <span>Drive ✓</span>
                      </span>
                    ) : (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        disabled={syncingDriveVoice !== null}
                        onClick={() => handleSyncVoiceToDrive(config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)")}
                        className="h-6 px-1.5 text-[11px] text-blue-300 hover:text-blue-200 hover:bg-blue-500/10 gap-1 rounded-md"
                        title="Sao lưu giọng đọc này lên Google Drive"
                      >
                        {syncingDriveVoice === (config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)") ? (
                          <RefreshCw className="w-3 h-3 animate-spin text-blue-400" />
                        ) : (
                          <Cloud className="w-3 h-3 text-blue-400" />
                        )}
                        <span className="text-[10px]">Lưu Drive</span>
                      </Button>
                    )}
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => handlePlayVoiceSample(config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)")}
                      className="h-6 px-1.5 text-[11px] text-amber-300 hover:text-amber-200 hover:bg-amber-500/10 gap-1 rounded-md"
                      title="Bấm để nghe thử giọng đọc mẫu"
                    >
                      {previewLoading && playingVoice === (config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)") ? (
                        <RefreshCw className="w-3 h-3 animate-spin text-amber-400" />
                      ) : playingVoice === (config.novel_tts_voice || config.tts_voice || "Ngọc Huyền (mới)") ? (
                        <>
                          <Square className="w-3 h-3 fill-current text-amber-400" />
                          <span className="text-[10px]">Dừng</span>
                        </>
                      ) : (
                        <>
                          <Volume2 className="w-3 h-3 text-amber-400" />
                          <span className="text-[10px]">Nghe thử</span>
                        </>
                      )}
                    </Button>
                    Tốc độ:
                    <Badge variant="outline" className="text-amber-300 border-amber-500/40 bg-amber-950/20 font-mono text-xs py-0.5 px-2">
                      {config.novel_tts_speed ?? config.tts_speed ?? 1.2}x
                    </Badge>
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setActiveTab("sub")}
                    className="text-[11px] text-purple-400 hover:text-purple-300 h-6 px-2 hover:bg-purple-950/30"
                  >
                    (Đổi giọng & chỉnh Whisper tại tab Phụ đề)
                  </Button>
                </div>

                <div className="flex items-center gap-4 shrink-0">
                  <div className="flex items-center space-x-2">
                    <Switch
                      id="novel_auto_open_capcut"
                      checked={config.auto_open_capcut ?? true}
                      onCheckedChange={(checked) => handleFieldChange("auto_open_capcut", checked)}
                      className="data-[state=checked]:bg-emerald-600"
                    />
                    <Label htmlFor="novel_auto_open_capcut" className="cursor-pointer text-[11px] font-medium text-emerald-400">
                      Mở CapCut sau B4
                    </Label>
                  </div>

                  <Button
                    type="button"
                    size="sm"
                    onClick={handleRunNovelPipeline}
                    disabled={novelLoading}
                    className="bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-600 hover:to-orange-700 text-zinc-950 font-bold text-xs h-8 px-4 gap-1.5 shadow-md shadow-amber-500/20"
                  >
                    <Sparkles className="w-3.5 h-3.5 fill-current text-zinc-950" />
                    <span>{novelLoading ? "Đang xử lý..." : "📖 Bắt đầu Tạo CapCut Draft"}</span>
                  </Button>
                </div>
              </Card>

                {/* Hiển thị kết quả sau khi chạy xong */}
                {novelDraftResult && novelDraftResult.draft_folder && (
                  <div className="p-3.5 rounded-xl bg-emerald-950/30 border border-emerald-500/50 space-y-2.5 animate-in fade-in-50">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex items-center gap-2 text-emerald-400 font-bold text-xs">
                        <CheckCircle className="w-4 h-4 text-emerald-400" />
                        <span>🎉 Đã sản xuất xong Dự Án CapCut Hoàn Chỉnh!</span>
                      </div>
                      <Button
                        type="button"
                        size="sm"
                        onClick={handleOpenCapCut}
                        className="h-8 px-3 bg-gradient-to-r from-emerald-500 to-teal-500 hover:opacity-90 text-zinc-950 font-bold text-xs rounded-lg shadow-md gap-1.5 shrink-0"
                      >
                        <Film className="w-3.5 h-3.5 fill-current" />
                        <span>🎬 Mở CapCut PC & Xuất Video</span>
                      </Button>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
                      <div className="p-2 rounded bg-black/40 border border-emerald-500/20">
                        <div className="text-[10px] text-zinc-400">Số câu phụ đề:</div>
                        <div className="text-emerald-300 font-bold text-sm">{novelDraftResult.sentences_count || 0} câu</div>
                      </div>
                      <div className="p-2 rounded bg-black/40 border border-emerald-500/20">
                        <div className="text-[10px] text-zinc-400">Ảnh phân cảnh phim:</div>
                        <div className="text-cyan-300 font-bold text-sm">{novelDraftResult.scenes_count || 0} ảnh 1080p</div>
                      </div>
                      <div className="p-2 rounded bg-black/40 border border-emerald-500/20">
                        <div className="text-[10px] text-zinc-400">Thời lượng video:</div>
                        <div className="text-amber-300 font-bold text-sm">{Math.floor((novelDraftResult.total_duration_sec || 0) / 60)}m {Math.round((novelDraftResult.total_duration_sec || 0) % 60)}s</div>
                      </div>
                      <div className="p-2 rounded bg-black/40 border border-emerald-500/20">
                        <div className="text-[10px] text-zinc-400">Tốc độ NghiTTS:</div>
                        <div className="text-purple-300 font-bold text-sm">{config.novel_tts_speed ?? 1.2}x</div>
                      </div>
                    </div>

                    <div className="p-2 rounded bg-black/50 border border-zinc-800 text-[11px] text-zinc-300 font-mono truncate flex items-center justify-between gap-2">
                      <span className="truncate">Thư mục CapCut: <strong>{novelDraftResult.draft_folder}</strong></span>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          navigator.clipboard.writeText(novelDraftResult.draft_folder);
                          toast.success("Đã sao chép đường dẫn dự án!");
                        }}
                        className="h-6 px-2 text-[10px] text-zinc-400 hover:text-white"
                      >
                        Copy
                      </Button>
                    </div>
                  </div>
                )}
              </div>
          </ErrorBoundary>
        )}

        {/* YouTube Auto-Publish Card - Shadcn Card & Switch */}
        <Card className="p-4 bg-gradient-to-r from-red-950/30 via-zinc-900/60 to-zinc-900/40 border border-red-500/20 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-red-500 font-bold text-lg">▶</span>
              <div>
                <div className="text-sm font-bold text-zinc-100 flex items-center gap-2">
                  Tự động Đăng YouTube sau khi Render xong
                  <Badge variant="outline" className="border-red-500/40 text-red-400 text-[10px] py-0">
                    Auto-Upload
                  </Badge>
                </div>
                <div className="text-xs text-zinc-400">
                  Video render xong sẽ được tự động tải thẳng lên kênh YouTube qua OAuth
                </div>
              </div>
            </div>
            <div className="flex items-center space-x-2">
              <Switch
                id="enable_auto_publish"
                checked={Boolean(config.enable_auto_publish)}
                onCheckedChange={(checked) => handleFieldChange("enable_auto_publish", checked)}
                className="data-[state=checked]:bg-red-600"
              />
            </div>
          </div>

          {config.enable_auto_publish && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-zinc-800/80 animate-in fade-in-50">
              <div>
                <Label htmlFor="youtube_title" className="block text-xs font-semibold text-zinc-300 mb-1">
                  Tiêu đề YouTube (Mặc định: Tên file):
                </Label>
                <Input
                  id="youtube_title"
                  type="text"
                  value={config.youtube_title || ""}
                  onChange={(e) => handleFieldChange("youtube_title", e.target.value)}
                  placeholder="Tiêu đề video YouTube #Shorts..."
                  className="bg-zinc-950/80 border-zinc-800 text-xs"
                />
              </div>
              <div>
                <Label htmlFor="youtube_description" className="block text-xs font-semibold text-zinc-300 mb-1">
                  Mô tả & Hashtags:
                </Label>
                <Input
                  id="youtube_description"
                  type="text"
                  value={config.youtube_description || ""}
                  onChange={(e) => handleFieldChange("youtube_description", e.target.value)}
                  placeholder="#Shorts #CapCut #Trending..."
                  className="bg-zinc-950/80 border-zinc-800 text-xs"
                />
              </div>
            </div>
          )}
        </Card>

        {/* Bottom Action Button */}
        <div className="pt-2 flex flex-col sm:flex-row gap-3">
          <Button
            type="button"
            size="lg"
            onClick={handleRunNovelPipeline}
            disabled={novelLoading}
            className="flex-1 py-4 text-sm rounded-2xl font-bold bg-gradient-to-r from-amber-500 via-orange-500 to-amber-600 hover:opacity-95 text-zinc-950 shadow-lg shadow-amber-500/25 gap-2"
          >
            <Sparkles className="w-5 h-5 fill-current" />
            <span>{novelLoading ? (novelStepMessage || "Đang sản xuất Pipeline 5 Bước...") : "📖 Chạy Thuyết Minh Tiểu Thuyết (Pipeline 5 Bước)"}</span>
          </Button>

          {novelDraftResult && (
            <Button
              type="button"
              size="lg"
              onClick={handleOpenCapCut}
              className="py-4 px-5 text-sm rounded-2xl font-bold bg-gradient-to-r from-emerald-500 to-teal-500 hover:opacity-95 text-zinc-950 shadow-lg shadow-emerald-500/25 gap-2"
            >
              <Film className="w-5 h-5 fill-current" />
              <span>🎬 Mở CapCut PC & Xuất</span>
            </Button>
          )}

          <Button
            type="button"
            size="lg"
            onClick={() => setTranslateModalOpen(true)}
            className="flex-1 py-4 text-sm rounded-2xl font-bold bg-gradient-to-r from-purple-600 to-[#622FF6] hover:opacity-95 text-white shadow-lg shadow-purple-500/25 gap-2"
          >
            <Languages className="w-5 h-5" />
            <span>🌐 Dịch Đa Ngôn Ngữ</span>
          </Button>

          <Button
            type="button"
            variant="gradient"
            size="lg"
            onClick={handleRunPipeline}
            className="flex-1 py-4 text-sm rounded-2xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white shadow-lg shadow-blue-500/20 gap-2"
          >
            <Play className="w-5 h-5 fill-current" />
            <span>▶ Chạy Pipeline ngay</span>
          </Button>
        </div>
      </Card>

      {/* Multi-Language Translation Modal */}
      <MultiLangTranslateModal
        open={translateModalOpen}
        onOpenChange={setTranslateModalOpen}
        folder={folder}
        currentConfig={config}
        onSuccess={onRunSuccess}
      />

      {/* Novel Library & Import Modal */}
      <NovelImportModal
        open={novelModalOpen}
        onOpenChange={setNovelModalOpen}
        selectedNovelId={selectedNovel?.id || "xianni"}
        onSelectNovel={(novel) => {
          setSelectedNovel(novel);
          setNovelModalOpen(false);
          toast.success(`Đã chọn bộ truyện: ${novel.name}`);
        }}
      />
    </div>
  );
};
