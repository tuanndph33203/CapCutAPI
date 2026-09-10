import React, { useState, useEffect, useRef } from "react";
import {
  BookOpen,
  FolderOpen,
  Sparkles,
  Search,
  FileText,
  Plus,
  Trash2,
  Copy,
  Save,
  Film,
  RefreshCw,
  Eye,
  ChevronRight,
  Flame,
  Wand2,
  ArrowLeft,
  Library,
  Layers,
  ExternalLink,
  CloudUpload,
  Cloud,
  Check,
  Clapperboard,
  Upload,
  Settings,
} from "lucide-react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from "./ui/table";
import { toast } from "sonner";
import axios from "axios";
import { NovelImportModal } from "./NovelImportModal";

interface Novel {
  id: string;
  name: string;
  chapters_count: number;
  path: string;
  source?: string;
}

interface Chapter {
  index: number;
  chapter_num: number;
  filename: string;
  title: string;
  search_keys?: string[];
  size_kb?: number;
}

interface ScriptItem {
  id: string;
  name: string;
  episode?: number | null;
  path: string;
  size_kb: number;
  modified_time: number;
  is_download?: boolean;
}

interface SceneItem {
  moment_index: number;
  start_time: number;
  end_time: number;
  target_frame_time?: number;
  highlight_type: string;
  importance_score: number;
  scene_title: string;
  srt_dialogue?: string;
  visual_description: string;
  tags: string[];
  thumbnail_url: string;
  keyframe_filename?: string;
}

interface AnalyzedEpisode {
  episode_dir: string;
  episode_num: number;
  scenes_count: number;
  path: string;
  has_metadata: boolean;
  drive_synced: boolean;
  drive_folder_link: string;
  last_synced_at?: number;
}

export const NovelsPage: React.FC = () => {
  const [novels, setNovels] = useState<Novel[]>([]);
  const [selectedNovel, setSelectedNovel] = useState<Novel | null>(null);
  const [searchNovelQuery, setSearchNovelQuery] = useState<string>("");
  const [activeTab, setActiveTab] = useState<"scripts" | "chapters" | "scenes">("scripts");
  const [isLoadingNovels, setIsLoadingNovels] = useState<boolean>(false);
  
  // Scripts State
  const [scripts, setScripts] = useState<ScriptItem[]>([]);
  const [selectedScriptName, setSelectedScriptName] = useState<string>("");
  const [scriptContent, setScriptContent] = useState<string>("");
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [isSavingScript, setIsSavingScript] = useState<boolean>(false);
  
  // Generation Params
  const [genEpisode, setGenEpisode] = useState<number>(190);
  const [genPrompt, setGenPrompt] = useState<string>("");

  // Chapters State
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [chapterSearch, setChapterSearch] = useState<string>("");
  const [selectedChapterFilename, setSelectedChapterFilename] = useState<string>("");
  const [chapterContent, setChapterContent] = useState<string>("");
  const [isLoadingChapters, setIsLoadingChapters] = useState<boolean>(false);

  // Scenes State (Whisper + AI + Vision + Google Drive)
  const [analyzedEpisodes, setAnalyzedEpisodes] = useState<AnalyzedEpisode[]>([]);
  const [selectedSceneEpisode, setSelectedSceneEpisode] = useState<number>(186);
  const [currentScenes, setCurrentScenes] = useState<SceneItem[]>([]);
  const [currentEpisodeMeta, setCurrentEpisodeMeta] = useState<any>(null);
  const [isAnalyzingScenes, setIsAnalyzingScenes] = useState<boolean>(false);
  const [isUploadingVideo, setIsUploadingVideo] = useState<boolean>(false);
  const [isSyncingDrive, setIsSyncingDrive] = useState<boolean>(false);
  const [sceneVideoPath, setSceneVideoPath] = useState<string>("");
  const [autoUploadDrive] = useState<boolean>(true);
  const [driveConfigOpen, setDriveConfigOpen] = useState<boolean>(false);
  const [driveConfig, setDriveConfig] = useState<any>({ client_id: "", refresh_token: "", target_folder_id: "" });

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Modal
  const [isNovelModalOpen, setIsNovelModalOpen] = useState<boolean>(false);

  // 1. Fetch Novels
  const loadNovels = async () => {
    setIsLoadingNovels(true);
    try {
      const res = await axios.get("/api/novel/list");
      if (res.data?.novels && res.data.novels.length > 0) {
        setNovels(res.data.novels);
      } else {
        setNovels([
          {
            id: "Pham nhan tu tien",
            name: "Phàm Nhân Tu Tiên (凡人修仙传)",
            chapters_count: 2375,
            path: "data/novels/Pham nhan tu tien/chapters",
            source: "imported"
          },
          {
            id: "xianni",
            name: "Tiên Nghịch (仙逆 - Nhĩ Căn)",
            chapters_count: 2073,
            path: "harnessNovel/my-novels/仙逆/reference/chapters",
            source: "builtin"
          }
        ]);
      }
    } catch (e) {
      console.error("Lỗi load danh sách truyện:", e);
      setNovels([
        {
          id: "Pham nhan tu tien",
          name: "Phàm Nhân Tu Tiên (凡人修仙传)",
          chapters_count: 2375,
          path: "data/novels/Pham nhan tu tien/chapters",
          source: "imported"
        },
        {
          id: "xianni",
          name: "Tiên Nghịch (仙逆 - Nhĩ Căn)",
          chapters_count: 2073,
          path: "harnessNovel/my-novels/仙逆/reference/chapters",
          source: "builtin"
        }
      ]);
    } finally {
      setIsLoadingNovels(false);
    }
  };

  useEffect(() => {
    loadNovels();
    loadGoogleDriveConfig();
  }, []);

  // 2. Fetch Scripts
  const loadScripts = async (novelId: string) => {
    try {
      const res = await axios.get(`/api/novel/scripts/list?novel_id=${encodeURIComponent(novelId)}`);
      if (res.data?.success) {
        const list: ScriptItem[] = res.data.scripts || [];
        setScripts(list);
        if (list.length > 0) {
          loadScriptContent(novelId, list[0].name);
        } else {
          setSelectedScriptName("");
          setScriptContent("");
        }
      }
    } catch (e) {
      console.error("Lỗi load scripts:", e);
    }
  };

  // 3. Load Script Content
  const loadScriptContent = async (novelId: string, name: string) => {
    setSelectedScriptName(name);
    try {
      const res = await axios.get(`/api/novel/scripts/get?novel_id=${encodeURIComponent(novelId)}&name=${encodeURIComponent(name)}`);
      if (res.data?.success) {
        setScriptContent(res.data.content || "");
      }
    } catch (e) {
      toast.error(`Không thể đọc nội dung kịch bản '${name}'`);
    }
  };

  // 4. Load Chapters
  const loadChapters = async (novelId: string) => {
    setIsLoadingChapters(true);
    try {
      const res = await axios.get(`/api/novel/chapters?novel_id=${encodeURIComponent(novelId)}`);
      if (res.data?.success) {
        setChapters(res.data.chapters || []);
        if (res.data.chapters?.length > 0) {
          loadChapterContent(novelId, res.data.chapters[0].filename);
        }
      }
    } catch (e) {
      console.error("Lỗi load chapters:", e);
    } finally {
      setIsLoadingChapters(false);
    }
  };

  // 5. Load Chapter Content
  const loadChapterContent = async (novelId: string, filename: string) => {
    setSelectedChapterFilename(filename);
    try {
      const res = await axios.get(`/api/novel/chapter?novel_id=${encodeURIComponent(novelId)}&filename=${encodeURIComponent(filename)}`);
      if (res.data?.success) {
        setChapterContent(res.data.content || "");
      }
    } catch (e) {
      toast.error(`Không thể đọc chương '${filename}'`);
    }
  };

  // 6. Load Scenes for novel
  const loadAnalyzedScenesList = async (novelId: string) => {
    try {
      const res = await axios.get(`/api/novel/scenes/list?novel_id=${encodeURIComponent(novelId)}`);
      if (res.data?.success) {
        const eps: AnalyzedEpisode[] = res.data.episodes || [];
        setAnalyzedEpisodes(eps);
        if (eps.length > 0) {
          loadEpisodeSceneDetails(novelId, eps[0].episode_num);
        } else {
          setCurrentScenes([]);
          setCurrentEpisodeMeta(null);
        }
      }
    } catch (e) {
      console.error("Lỗi load scenes list:", e);
    }
  };

  // 7. Load Episode Scene Details
  const loadEpisodeSceneDetails = async (novelId: string, episodeNum: number) => {
    setSelectedSceneEpisode(episodeNum);
    try {
      const res = await axios.get(`/api/novel/scenes/details?novel_id=${encodeURIComponent(novelId)}&episode=${episodeNum}`);
      if (res.data?.success) {
        setCurrentScenes(res.data.scenes || []);
        setCurrentEpisodeMeta(res.data);
      }
    } catch (e) {
      console.error("Lỗi load scene details:", e);
    }
  };

  // 8. Load Google Drive Config
  const loadGoogleDriveConfig = async () => {
    try {
      const res = await axios.get("/api/google_drive/config");
      if (res.data?.success) {
        setDriveConfig(res.data.config || {});
      }
    } catch (e) {
      console.error("Lỗi load Google Drive config:", e);
    }
  };

  // Select Novel Detail
  const handleSelectNovelDetail = (novel: Novel) => {
    setSelectedNovel(novel);
    loadScripts(novel.id);
    loadChapters(novel.id);
    loadAnalyzedScenesList(novel.id);
  };

  // Delete Novel
  const handleDeleteNovel = async (novelId: string, novelName: string) => {
    if (!window.confirm(`Bạn có chắc chắn muốn xóa bộ truyện '${novelName}' khỏi hệ thống không?`)) {
      return;
    }
    try {
      const res = await axios.post("/api/novel/delete", { novel_id: novelId });
      if (res.data?.success) {
        toast.success(`Đã xóa thành công bộ truyện '${novelName}'!`);
        if (selectedNovel?.id === novelId) {
          setSelectedNovel(null);
        }
        loadNovels();
      } else {
        toast.error("Không thể xóa bộ truyện", { description: res.data?.error || "Lỗi không xác định" });
      }
    } catch (e: any) {
      toast.error("Lỗi xóa bộ truyện", { description: e.response?.data?.error || e.message });
    }
  };

  // Save Script
  const handleSaveScript = async () => {
    if (!selectedNovel) return;
    if (!selectedScriptName.trim()) {
      toast.error("Vui lòng đặt tên cho kịch bản!");
      return;
    }
    setIsSavingScript(true);
    try {
      const res = await axios.post("/api/novel/scripts/save", {
        novel_id: selectedNovel.id,
        name: selectedScriptName,
        content: scriptContent
      });
      if (res.data?.success) {
        toast.success(res.data.message || "Đã lưu kịch bản thành công!");
        loadScripts(selectedNovel.id);
      }
    } catch (e: any) {
      toast.error("Lỗi lưu kịch bản", { description: e.response?.data?.error || e.message });
    } finally {
      setIsSavingScript(false);
    }
  };

  // Generate Script AI
  const handleGenerateScriptAI = async () => {
    if (!selectedNovel) return;
    setIsGenerating(true);
    toast.info(`Đang sinh kịch bản Review cho Tập ${genEpisode}...`);
    try {
      const res = await axios.post("/api/novel/generate_script_text", {
        novel_id: selectedNovel.id,
        current_episode_num: genEpisode - 1,
        prompt: genPrompt || `tập ${genEpisode}`
      });
      if (res.data?.success && res.data.full_plain_text) {
        const newContent = res.data.full_plain_text;
        const newName = `Tap_${genEpisode}_Review_Master.txt`;
        setScriptContent(newContent);
        setSelectedScriptName(newName);
        
        await axios.post("/api/novel/scripts/save", {
          novel_id: selectedNovel.id,
          name: newName,
          content: newContent
        });
        
        toast.success(`Đã sinh xong kịch bản Tập ${genEpisode}! (${res.data.scenes_count || 0} câu)`);
        loadScripts(selectedNovel.id);
      } else {
        toast.error("Không thể sinh kịch bản", { description: res.data?.error || "Lỗi không xác định" });
      }
    } catch (e: any) {
      toast.error("Lỗi sinh kịch bản AI", { description: e.response?.data?.error || e.message });
    } finally {
      setIsGenerating(false);
    }
  };

  // Delete Script
  const handleDeleteScript = async (name: string) => {
    if (!selectedNovel) return;
    if (!window.confirm(`Bạn có chắc chắn muốn xóa kịch bản '${name}' không?`)) return;
    try {
      const res = await axios.post("/api/novel/scripts/delete", {
        novel_id: selectedNovel.id,
        name: name
      });
      if (res.data?.success) {
        toast.success(`Đã xóa kịch bản '${name}'`);
        loadScripts(selectedNovel.id);
      }
    } catch (e: any) {
      toast.error("Lỗi xóa kịch bản", { description: e.response?.data?.error || e.message });
    }
  };

  // Upload Video for Scenes
  const handleUploadVideoFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selectedNovel) return;
    
    setIsUploadingVideo(true);
    toast.info(`Đang tải lên video '${file.name}'...`);
    const formData = new FormData();
    formData.append("video", file);
    formData.append("novel_id", selectedNovel.id);
    formData.append("episode_num", String(selectedSceneEpisode));

    try {
      const res = await axios.post("/api/novel/scenes/upload_video", formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      if (res.data?.success) {
        toast.success("Tải lên video thành công!");
        setSceneVideoPath(res.data.path);
      } else {
        toast.error("Lỗi tải lên video", { description: res.data?.error });
      }
    } catch (err: any) {
      toast.error("Lỗi upload video", { description: err.message });
    } finally {
      setIsUploadingVideo(false);
    }
  };

  // RUN FULL SCENE ANALYSIS PIPELINE (Whisper + AI + Vision + DB + Google Drive)
  const handleRunFullScenePipeline = async () => {
    if (!selectedNovel) return;
    setIsAnalyzingScenes(true);
    toast.info(`Bắt đầu chạy AI phân cảnh cho Tập ${selectedSceneEpisode}...`, {
      description: "1. Whisper phụ đề -> 2. AI nhận xét mốc nổi bật -> 3. Cắt ảnh keyframes -> 4. Mô tả cảnh -> 5. Đẩy lên Google Drive"
    });

    try {
      const res = await axios.post("/api/novel/scenes/full_pipeline", {
        novel_id: selectedNovel.id,
        novel_name: selectedNovel.name,
        episode_num: selectedSceneEpisode,
        video_path: sceneVideoPath || undefined,
        auto_upload_drive: autoUploadDrive
      });

      if (res.data?.success) {
        toast.success(`Đã phân tích xong ${res.data.scenes_count} phân cảnh nổi bật cho Tập ${selectedSceneEpisode}! 🎉`);
        if (res.data.drive_synced && res.data.drive_folder_link) {
          toast.success("☁️ Đã tải toàn bộ ảnh phân cảnh lên Google Drive thành công!");
        }
        loadAnalyzedScenesList(selectedNovel.id);
        loadEpisodeSceneDetails(selectedNovel.id, selectedSceneEpisode);
      } else {
        toast.error("Lỗi phân tích phân cảnh", { description: res.data?.error || "Lỗi không xác định" });
      }
    } catch (e: any) {
      toast.error("Lỗi xử lý phân cảnh AI", { description: e.response?.data?.error || e.message });
    } finally {
      setIsAnalyzingScenes(false);
    }
  };

  // Sync to Google Drive directly
  const handleSyncToDrive = async () => {
    if (!selectedNovel) return;
    setIsSyncingDrive(true);
    toast.info(`Đang tải toàn bộ ảnh phân cảnh Tập ${selectedSceneEpisode} lên Google Drive...`);
    try {
      const res = await axios.post("/api/novel/scenes/upload_drive", {
        novel_id: selectedNovel.id,
        novel_name: selectedNovel.name,
        episode_num: selectedSceneEpisode,
        sync_keyframes: true,
        sync_clips: false
      });
      if (res.data?.success) {
        toast.success(`Đã đẩy thành công ${res.data.uploaded_count} file lên Google Drive!`);
        loadAnalyzedScenesList(selectedNovel.id);
        loadEpisodeSceneDetails(selectedNovel.id, selectedSceneEpisode);
      } else {
        toast.error("Lỗi đẩy lên Google Drive", { description: res.data?.error });
      }
    } catch (e: any) {
      toast.error("Lỗi kết nối Google Drive", { description: e.message });
    } finally {
      setIsSyncingDrive(false);
    }
  };

  // Save Google Drive Config
  const handleSaveDriveConfig = async () => {
    try {
      const res = await axios.post("/api/google_drive/config", driveConfig);
      if (res.data?.success) {
        toast.success("Đã lưu cấu hình Google Drive thành công!");
        setDriveConfigOpen(false);
      }
    } catch (e: any) {
      toast.error("Lỗi lưu cấu hình Google Drive", { description: e.message });
    }
  };

  // Filter Novels
  const filteredNovels = novels.filter((n) => {
    if (!searchNovelQuery.trim()) return true;
    return (
      n.name.toLowerCase().includes(searchNovelQuery.toLowerCase()) ||
      n.id.toLowerCase().includes(searchNovelQuery.toLowerCase())
    );
  });

  // Filter Chapters
  const filteredChapters = chapters.filter((c) => {
    if (!chapterSearch.trim()) return true;
    const q = chapterSearch.toLowerCase();
    return (
      c.title.toLowerCase().includes(q) ||
      String(c.chapter_num).includes(q) ||
      (c.search_keys && c.search_keys.some((k) => k.toLowerCase().includes(q)))
    );
  });

  // ==========================================
  // VIEW 1: MÀN HÌNH DANH SÁCH BỘ TRUYỆN DẠNG TABLE SHADCN UI
  // ==========================================
  if (!selectedNovel) {
    return (
      <div className="space-y-5 pb-12">
        {/* Compact Header Bar */}
        <div className="p-4 rounded-2xl bg-zinc-900/90 border border-zinc-800 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-lg">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/30">
              <Library className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-bold text-white tracking-tight">
                  Thư Viện Tiểu Thuyết & Kịch Bản AI
                </h1>
                <Badge className="bg-amber-500/20 text-amber-300 border-amber-500/30 text-[11px] font-mono">
                  {novels.length} Bộ Truyện
                </Badge>
              </div>
              <p className="text-xs text-zinc-400">
                Quản lý kho tiểu thuyết nguyên tác, danh sách chương và biên tập kịch bản Review từng tập
              </p>
            </div>
          </div>

          {/* Action Button: Nhập Truyện Mới (Nhỏ gọn) */}
          <div className="flex items-center gap-2 self-start sm:self-auto">
            <Button
              type="button"
              size="sm"
              onClick={() => setIsNovelModalOpen(true)}
              className="bg-amber-500 hover:bg-amber-600 text-black font-bold text-xs h-8 px-3 gap-1.5 rounded-xl shadow-md"
            >
              <Plus className="w-3.5 h-3.5" />
              Nhập Truyện Mới
            </Button>

            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={loadNovels}
              className="border-zinc-700 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs h-8 px-2.5 rounded-xl"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoadingNovels ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </div>

        {/* Search Bar */}
        <div className="flex items-center gap-3">
          <div className="relative flex-1 max-w-sm">
            <Search className="w-3.5 h-3.5 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <Input
              type="text"
              value={searchNovelQuery}
              onChange={(e) => setSearchNovelQuery(e.target.value)}
              placeholder="Tìm kiếm bộ truyện (vd: Phàm Nhân, Tiên Nghịch)..."
              className="pl-8 bg-zinc-900/80 border-zinc-800 text-xs h-8 rounded-xl text-white"
            />
          </div>
        </div>

        {/* SHADCN UI TABLE: LIST TRUYỆN GỌN NHẸ */}
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/60 overflow-hidden shadow-xl">
          <Table>
            <TableHeader className="bg-zinc-900/90">
              <TableRow className="border-zinc-800">
                <TableHead className="w-[80px] text-center font-bold">#</TableHead>
                <TableHead className="font-bold">Tên Bộ Truyện</TableHead>
                <TableHead className="font-bold text-center w-[180px]">Số Chương</TableHead>
                <TableHead className="text-right font-bold pr-6 w-[200px]">Thao Tác</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredNovels.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="text-center py-12 text-zinc-500 text-xs">
                    {isLoadingNovels ? "Đang tải danh sách bộ truyện..." : "Không tìm thấy bộ truyện nào. Hãy bấm 'Nhập Truyện Mới' để thêm truyện!"}
                  </TableCell>
                </TableRow>
              ) : (
                filteredNovels.map((novel, idx) => {
                  const isPhamNhan = novel.id.toLowerCase().includes("pham") || novel.name.toLowerCase().includes("phàm");
                  const isTienNghich = novel.id.toLowerCase().includes("xianni") || novel.name.toLowerCase().includes("tiên nghịch");

                  return (
                    <TableRow
                      key={novel.id}
                      onClick={() => handleSelectNovelDetail(novel)}
                      className="cursor-pointer hover:bg-amber-500/5 transition-colors border-zinc-800/80 group"
                    >
                      {/* Icon / STT */}
                      <TableCell className="text-center">
                        <div className={`w-8 h-8 mx-auto rounded-lg flex items-center justify-center font-bold text-xs shadow-sm ${
                          isPhamNhan
                            ? "bg-gradient-to-br from-amber-500 to-orange-700 text-black border border-amber-400/50"
                            : isTienNghich
                            ? "bg-gradient-to-br from-blue-600 to-indigo-900 text-white border border-blue-400/50"
                            : "bg-zinc-800 text-amber-400 border border-zinc-700"
                        }`}>
                          {isPhamNhan ? "凡" : isTienNghich ? "仙" : idx + 1}
                        </div>
                      </TableCell>

                      {/* Tên truyện */}
                      <TableCell>
                        <div className="space-y-0.5">
                          <span className="font-bold text-sm text-zinc-100 group-hover:text-amber-300 transition-colors">
                            {novel.name}
                          </span>
                          <p className="text-[11px] font-mono text-zinc-400">
                            Mã: {novel.id}
                          </p>
                        </div>
                      </TableCell>

                      {/* Số chương */}
                      <TableCell className="text-center">
                        <Badge className="bg-amber-500/20 text-amber-300 border-amber-500/30 text-xs font-mono px-3 py-1">
                          {novel.chapters_count?.toLocaleString()} Chương
                        </Badge>
                      </TableCell>

                      {/* Action */}
                      <TableCell className="text-right pr-6">
                        <div className="flex items-center justify-end gap-2">
                          <Button
                            type="button"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleSelectNovelDetail(novel);
                            }}
                            className="bg-amber-500/15 hover:bg-amber-500 text-amber-300 hover:text-black font-bold text-xs h-8 px-3 gap-1.5 rounded-lg border border-amber-500/30 transition-all shadow-sm"
                          >
                            <Sparkles className="w-3.5 h-3.5" />
                            Mở Kịch Bản
                            <ChevronRight className="w-3.5 h-3.5" />
                          </Button>

                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteNovel(novel.id, novel.name);
                            }}
                            className="border-red-500/30 bg-red-500/10 hover:bg-red-500 hover:text-white text-red-400 font-bold text-xs h-8 px-2.5 rounded-lg transition-all shadow-sm"
                            title="Xóa bộ truyện"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </div>

        {/* Novel Import Modal */}
        <NovelImportModal
          open={isNovelModalOpen}
          onOpenChange={setIsNovelModalOpen}
          selectedNovelId="Pham nhan tu tien"
          onSelectNovel={(novel) => {
            loadNovels();
            handleSelectNovelDetail(novel);
          }}
        />
      </div>
    );
  }

  // ==========================================
  // VIEW 2: MÀN HÌNH CHI TIẾT BỘ TRUYỆN & KỊCH BẢN (DETAIL)
  // ==========================================
  return (
    <div className="space-y-5 pb-12">
      {/* Top Navigation & Back Button */}
      <div className="p-4 rounded-2xl bg-zinc-900/90 border border-zinc-800 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-lg">
        <div className="flex items-center gap-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setSelectedNovel(null)}
            className="border-zinc-700 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs h-8 px-2.5 gap-1.5 rounded-xl shadow-sm"
          >
            <ArrowLeft className="w-3.5 h-3.5 text-amber-400" />
            Danh Sách Truyện
          </Button>

          <div className="h-4 w-[1px] bg-zinc-700 hidden sm:block" />

          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold text-white">
                {selectedNovel.name}
              </h1>
              <Badge className="bg-amber-500/20 text-amber-300 border-amber-500/40 font-mono text-[10px] px-2">
                {selectedNovel.chapters_count?.toLocaleString()} Chương
              </Badge>
            </div>
            <p className="text-[11px] text-zinc-400">
              Quản lý kịch bản Review, phân cảnh phim AI & đồng bộ Google Drive
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            onClick={() => setIsNovelModalOpen(true)}
            variant="outline"
            className="border-amber-500/40 bg-zinc-900 text-amber-300 text-xs h-8 gap-1.5 rounded-xl"
          >
            <FolderOpen className="w-3.5 h-3.5" />
            Đổi / Nhập Thêm
          </Button>

          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => handleDeleteNovel(selectedNovel.id, selectedNovel.name)}
            className="border-red-500/40 bg-red-500/10 hover:bg-red-500 hover:text-white text-red-400 text-xs h-8 gap-1.5 rounded-xl"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Xóa Truyện
          </Button>
        </div>
      </div>

      {/* Main Tabs Navigation (3 TABS) */}
      <div className="flex items-center gap-2 border-b border-zinc-800 pb-2 overflow-x-auto">
        <button
          onClick={() => setActiveTab("scripts")}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-xl font-bold text-xs transition-all whitespace-nowrap ${
            activeTab === "scripts"
              ? "bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm"
              : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50"
          }`}
        >
          <Flame className="w-3.5 h-3.5 text-amber-400" />
          ✍️ Kho Kịch Bản Review & Thuyết Minh ({scripts.length})
        </button>

        <button
          onClick={() => setActiveTab("scenes")}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-xl font-bold text-xs transition-all whitespace-nowrap ${
            activeTab === "scenes"
              ? "bg-gradient-to-r from-purple-500/20 to-pink-500/20 text-purple-300 border border-purple-500/40 shadow-sm"
              : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50"
          }`}
        >
          <Clapperboard className="w-3.5 h-3.5 text-purple-400" />
          🎬 Phân Cảnh Phim AI & Google Drive ({analyzedEpisodes.length} tập)
        </button>

        <button
          onClick={() => setActiveTab("chapters")}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-xl font-bold text-xs transition-all whitespace-nowrap ${
            activeTab === "chapters"
              ? "bg-blue-500/20 text-blue-300 border border-blue-500/40 shadow-sm"
              : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50"
          }`}
        >
          <BookOpen className="w-3.5 h-3.5 text-blue-400" />
          📖 Nguyên Tác Chương Truyện ({selectedNovel.chapters_count?.toLocaleString() || chapters.length})
        </button>
      </div>

      {/* TAB 1: SCRIPTS STUDIO */}
      {activeTab === "scripts" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          {/* Left Column: Script List & Generator (4 cols) */}
          <div className="lg:col-span-4 space-y-4">
            {/* Quick Generator Box */}
            <div className="p-3.5 rounded-2xl bg-zinc-900/80 border border-amber-500/30 space-y-3 shadow-md">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold text-amber-400 flex items-center gap-1.5">
                  <Wand2 className="w-3.5 h-3.5" /> ⚡ Sinh Kịch Bản Tập Mới
                </h3>
                <Badge className="bg-amber-500/20 text-amber-300 text-[10px]">AI Studio</Badge>
              </div>

              <div className="grid grid-cols-3 gap-2">
                <div className="col-span-1 space-y-1">
                  <span className="text-[10px] text-zinc-400 font-semibold">Tập Phim:</span>
                  <Input
                    type="number"
                    value={genEpisode}
                    onChange={(e) => setGenEpisode(parseInt(e.target.value) || 1)}
                    className="bg-black/60 border-zinc-700 text-amber-300 font-bold text-xs h-8 rounded-lg"
                  />
                </div>
                <div className="col-span-2 space-y-1">
                  <span className="text-[10px] text-zinc-400 font-semibold">Prompt chỉ đạo (tùy chọn):</span>
                  <Input
                    type="text"
                    value={genPrompt}
                    onChange={(e) => setGenPrompt(e.target.value)}
                    placeholder="vd: Chương 698, đại chiến Mộ Lan..."
                    className="bg-black/60 border-zinc-700 text-zinc-200 text-xs h-8 rounded-lg"
                  />
                </div>
              </div>

              <Button
                type="button"
                onClick={handleGenerateScriptAI}
                disabled={isGenerating}
                className="w-full bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-black font-extrabold text-xs h-8 gap-2 rounded-xl shadow-md"
              >
                {isGenerating ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    Đang Biên Kịch AI...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3.5 h-3.5" />
                    ⚡ Sinh Kịch Bản Tập {genEpisode} Ngay
                  </>
                )}
              </Button>
            </div>

            {/* Saved Scripts List */}
            <div className="p-3.5 rounded-2xl bg-zinc-900/60 border border-zinc-800 space-y-2.5">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold text-zinc-300 flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-amber-400" />
                  Danh Sách Kịch Bản ({scripts.length})
                </h3>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => loadScripts(selectedNovel.id)}
                  className="h-6 w-6 p-0 text-zinc-400 hover:text-white"
                >
                  <RefreshCw className="w-3 h-3" />
                </Button>
              </div>

              <div className="space-y-1.5 max-h-[480px] overflow-y-auto pr-1">
                {scripts.length === 0 ? (
                  <div className="text-center py-8 text-zinc-500 text-xs">
                    Chưa có file kịch bản nào. Hãy bấm nút Sinh kịch bản ở trên!
                  </div>
                ) : (
                  scripts.map((sc) => (
                    <div
                      key={sc.id}
                      onClick={() => loadScriptContent(selectedNovel.id, sc.name)}
                      className={`p-2.5 rounded-xl border text-xs cursor-pointer transition-all flex items-center justify-between gap-2 ${
                        selectedScriptName === sc.name
                          ? "bg-amber-500/15 border-amber-500/50 text-amber-300 font-bold shadow-sm"
                          : "bg-black/40 border-zinc-800 text-zinc-300 hover:border-zinc-700 hover:bg-zinc-800/40"
                      }`}
                    >
                      <div className="flex items-center gap-2 truncate">
                        <FileText className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                        <span className="truncate">{sc.name}</span>
                        {sc.episode && (
                          <Badge className="bg-amber-500/20 text-amber-300 text-[9px] px-1.5 py-0">
                            Tập {sc.episode}
                          </Badge>
                        )}
                        {sc.is_download && (
                          <Badge className="bg-blue-500/20 text-blue-300 text-[9px] px-1 py-0">
                            Downloads
                          </Badge>
                        )}
                      </div>

                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteScript(sc.name);
                        }}
                        className="text-zinc-500 hover:text-red-400 p-1 rounded transition-colors"
                        title="Xóa kịch bản"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* Right Column: Full Script Editor (8 cols) */}
          <div className="lg:col-span-8 space-y-4">
            <div className="p-4 rounded-2xl bg-zinc-900/80 border border-zinc-800 space-y-3 shadow-lg flex flex-col h-full">
              {/* Header Editor Controls */}
              <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-zinc-800">
                <div className="flex items-center gap-2 flex-1 min-w-[220px]">
                  <span className="text-xs font-bold text-zinc-400 shrink-0">Tên file:</span>
                  <Input
                    type="text"
                    value={selectedScriptName}
                    onChange={(e) => setSelectedScriptName(e.target.value)}
                    placeholder="Tap_190_Review_Master.txt"
                    className="bg-black/60 border-zinc-700 text-amber-300 font-bold text-xs h-8 rounded-lg"
                  />
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => {
                      navigator.clipboard.writeText(scriptContent);
                      toast.success("Đã sao chép toàn bộ kịch bản vào Clipboard!");
                    }}
                    variant="outline"
                    className="border-zinc-700 bg-zinc-800 text-zinc-200 text-xs h-8 gap-1.5 rounded-xl"
                  >
                    <Copy className="w-3.5 h-3.5" />
                    Sao Chép
                  </Button>

                  <Button
                    type="button"
                    size="sm"
                    onClick={handleSaveScript}
                    disabled={isSavingScript}
                    className="bg-amber-500 hover:bg-amber-600 text-black font-bold text-xs h-8 gap-1.5 rounded-xl shadow-sm"
                  >
                    <Save className="w-3.5 h-3.5" />
                    {isSavingScript ? "Đang lưu..." : "Lưu Kịch Bản"}
                  </Button>
                </div>
              </div>

              {/* Textarea Monospace Editor */}
              <div className="space-y-1 flex-1 flex flex-col">
                <div className="flex items-center justify-between text-[11px] text-zinc-400">
                  <span>Mỗi câu 1 dòng • Khoảng nghỉ [0.2], [0.5]</span>
                  <span>{scriptContent.split("\n").filter(l => l.trim() && !l.startsWith("[")).length} câu thoại</span>
                </div>
                <textarea
                  value={scriptContent}
                  onChange={(e) => setScriptContent(e.target.value)}
                  placeholder="Nội dung kịch bản review thuyết minh sẽ hiển thị ở đây..."
                  rows={22}
                  className="w-full p-4 rounded-xl bg-black/90 border border-zinc-800 font-mono text-xs text-zinc-200 leading-relaxed outline-none focus:border-amber-500/60 focus:ring-1 focus:ring-amber-500/30 transition-all resize-y"
                  style={{ minHeight: "480px" }}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: SCENE ANALYSIS & GOOGLE DRIVE STUDIO (NEW!) */}
      {activeTab === "scenes" && (
        <div className="space-y-5">
          {/* Top Control Action Bar: Upload Video, Episode, and AI Execution */}
          <div className="p-4 rounded-2xl bg-gradient-to-r from-purple-950/40 via-zinc-900 to-zinc-900 border border-purple-500/30 shadow-xl space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-purple-500/20 text-purple-300 border border-purple-500/40 shadow-inner">
                  <Clapperboard className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-sm font-bold text-white flex items-center gap-2">
                    AI Phân Tích Phân Cảnh Tập Phim & Đồng Bộ Google Drive
                    <Badge className="bg-purple-500/20 text-purple-300 border-purple-500/30 text-[10px]">
                      Whisper + Vision + Cloud
                    </Badge>
                  </h2>
                  <p className="text-xs text-zinc-400">
                    Tự động chạy Whisper tách phụ đề SRT $\rightarrow$ AI nhận xét khoảnh khắc nổi bật $\rightarrow$ Trích xuất Keyframe $\rightarrow$ Mô tả cảnh $\rightarrow$ Đẩy lên Google Drive
                  </p>
                </div>
              </div>

              {/* Google Drive Status & Settings */}
              <div className="flex items-center gap-2 self-start md:self-auto">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setDriveConfigOpen(true)}
                  className="border-zinc-700 bg-zinc-800/80 text-zinc-300 text-xs h-8 gap-1.5 rounded-xl hover:text-white"
                >
                  <Settings className="w-3.5 h-3.5 text-zinc-400" />
                  Cấu Hình Google Drive
                </Button>
              </div>
            </div>

            {/* Input Controls */}
            <div className="grid grid-cols-1 md:grid-cols-12 gap-3 pt-2 border-t border-zinc-800">
              {/* Episode Number */}
              <div className="md:col-span-2 space-y-1">
                <span className="text-[11px] text-zinc-400 font-semibold">Tập Phim:</span>
                <Input
                  type="number"
                  value={selectedSceneEpisode}
                  onChange={(e) => setSelectedSceneEpisode(parseInt(e.target.value) || 1)}
                  className="bg-black/60 border-zinc-700 text-purple-300 font-bold text-xs h-8 rounded-lg"
                />
              </div>

              {/* Upload or Choose Video */}
              <div className="md:col-span-6 space-y-1">
                <span className="text-[11px] text-zinc-400 font-semibold">File Video Tập Phim (Hoặc tự quét Downloads):</span>
                <div className="flex items-center gap-2">
                  <Input
                    type="text"
                    value={sceneVideoPath}
                    onChange={(e) => setSceneVideoPath(e.target.value)}
                    placeholder="Để trống để tự tìm trong thư mục Downloads hoặc chọn file bên phải..."
                    className="bg-black/60 border-zinc-700 text-zinc-200 text-xs h-8 rounded-lg flex-1"
                  />
                  <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleUploadVideoFile}
                    accept="video/mp4,video/mkv,video/avi"
                    className="hidden"
                  />
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isUploadingVideo}
                    variant="outline"
                    className="border-purple-500/40 bg-purple-500/10 hover:bg-purple-500/20 text-purple-300 text-xs h-8 px-3 gap-1.5 rounded-lg shrink-0"
                  >
                    <Upload className="w-3.5 h-3.5" />
                    {isUploadingVideo ? "Đang tải..." : "Tải Video Lên"}
                  </Button>
                </div>
              </div>

              {/* Action Button: Run Full Pipeline */}
              <div className="md:col-span-4 flex items-end">
                <Button
                  type="button"
                  onClick={handleRunFullScenePipeline}
                  disabled={isAnalyzingScenes}
                  className="w-full bg-gradient-to-r from-purple-600 via-pink-600 to-amber-500 hover:from-purple-700 hover:to-amber-600 text-white font-extrabold text-xs h-8 gap-2 rounded-xl shadow-lg transition-all"
                >
                  {isAnalyzingScenes ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      Đang Whisper & Phân Tích Cảnh AI...
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-3.5 h-3.5" />
                      ⚡ Chạy Phân Cảnh AI & Đẩy Lên Drive
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>

          {/* Main Layout: List Episodes (3 cols) & Scene Cards Grid (9 cols) */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            {/* Left Column: Analyzed Episodes List (3 cols) */}
            <div className="lg:col-span-3 space-y-3">
              <div className="p-3.5 rounded-2xl bg-zinc-900/80 border border-zinc-800 space-y-2.5 shadow-md">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold text-zinc-300 flex items-center gap-1.5">
                    <Layers className="w-3.5 h-3.5 text-purple-400" />
                    Tập Đã Phân Tích ({analyzedEpisodes.length})
                  </h3>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => loadAnalyzedScenesList(selectedNovel.id)}
                    className="h-6 w-6 p-0 text-zinc-400 hover:text-white"
                  >
                    <RefreshCw className="w-3 h-3" />
                  </Button>
                </div>

                <div className="space-y-1.5 max-h-[560px] overflow-y-auto pr-1">
                  {analyzedEpisodes.length === 0 ? (
                    <div className="text-center py-10 text-zinc-500 text-xs">
                      Chưa có tập nào được phân tích. Hãy chọn tập và bấm nút Chạy ở trên!
                    </div>
                  ) : (
                    analyzedEpisodes.map((ep) => (
                      <div
                        key={ep.episode_dir}
                        onClick={() => loadEpisodeSceneDetails(selectedNovel.id, ep.episode_num)}
                        className={`p-2.5 rounded-xl border text-xs cursor-pointer transition-all space-y-1 ${
                          selectedSceneEpisode === ep.episode_num
                            ? "bg-purple-500/20 border-purple-500/60 text-purple-200 font-bold shadow-md"
                            : "bg-black/40 border-zinc-800 text-zinc-300 hover:border-zinc-700 hover:bg-zinc-800/40"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-white font-bold">Tập {ep.episode_num}</span>
                          <Badge className="bg-purple-500/20 text-purple-300 text-[9px] px-1.5 py-0">
                            {ep.scenes_count} Cảnh
                          </Badge>
                        </div>

                        <div className="flex items-center justify-between text-[10px]">
                          {ep.drive_synced ? (
                            <span className="text-emerald-400 flex items-center gap-1 font-semibold">
                              <Check className="w-3 h-3" /> Đã Lên GG Drive
                            </span>
                          ) : (
                            <span className="text-zinc-500">Chưa lên Drive</span>
                          )}

                          {ep.drive_folder_link && (
                            <a
                              href={ep.drive_folder_link}
                              target="_blank"
                              rel="noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="text-blue-400 hover:underline flex items-center gap-0.5"
                            >
                              <ExternalLink className="w-2.5 h-2.5" /> Mở Drive
                            </a>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>

            {/* Right Column: Scenes Grid (9 cols) */}
            <div className="lg:col-span-9 space-y-4">
              {currentEpisodeMeta && (
                <div className="p-3.5 rounded-2xl bg-zinc-900/90 border border-zinc-800 flex flex-wrap items-center justify-between gap-3 shadow-md">
                  <div className="flex items-center gap-3">
                    <h3 className="text-xs font-bold text-white flex items-center gap-1.5">
                      <Film className="w-3.5 h-3.5 text-purple-400" />
                      Chi Tiết Phân Cảnh Tập {selectedSceneEpisode} ({currentScenes.length} Phân Cảnh Nổi Bật)
                    </h3>
                    {currentEpisodeMeta.video_filename && (
                      <span className="text-[11px] text-zinc-400 font-mono">
                        (Nguồn: {currentEpisodeMeta.video_filename})
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    {currentEpisodeMeta.drive_folder_link && (
                      <a
                        href={currentEpisodeMeta.drive_folder_link}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/40 text-xs font-bold transition-all shadow-sm"
                      >
                        <Cloud className="w-3.5 h-3.5 text-blue-400" />
                        Mở Thư Mục Google Drive
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}

                    <Button
                      type="button"
                      size="sm"
                      onClick={handleSyncToDrive}
                      disabled={isSyncingDrive}
                      className="bg-purple-600 hover:bg-purple-700 text-white font-bold text-xs h-7 px-3 gap-1.5 rounded-xl shadow-sm"
                    >
                      <CloudUpload className={`w-3.5 h-3.5 ${isSyncingDrive ? "animate-bounce" : ""}`} />
                      {isSyncingDrive ? "Đang đẩy lên Drive..." : "Đẩy Lên Google Drive"}
                    </Button>
                  </div>
                </div>
              )}

              {/* Scenes Cards Grid */}
              {currentScenes.length === 0 ? (
                <div className="p-12 rounded-2xl bg-zinc-900/40 border border-zinc-800 text-center space-y-3">
                  <Clapperboard className="w-10 h-10 text-zinc-600 mx-auto" />
                  <p className="text-xs text-zinc-400">
                    Chưa có phân cảnh nào cho Tập {selectedSceneEpisode}. Hãy tải video lên và bấm nút "Chạy Phân Cảnh AI & Đẩy Lên Drive"!
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                  {currentScenes.map((scene, sIdx) => {
                    const highlightColor =
                      scene.highlight_type === "combat"
                        ? "bg-red-500/20 text-red-300 border-red-500/40"
                        : scene.highlight_type === "breakthrough"
                        ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                        : scene.highlight_type === "dialogue"
                        ? "bg-blue-500/20 text-blue-300 border-blue-500/40"
                        : "bg-purple-500/20 text-purple-300 border-purple-500/40";

                    return (
                      <div
                        key={sIdx}
                        className="rounded-2xl border border-zinc-800 bg-zinc-900/80 overflow-hidden shadow-lg hover:border-purple-500/50 transition-all group flex flex-col justify-between"
                      >
                        {/* Image Preview */}
                        <div className="relative aspect-video bg-black/80 overflow-hidden">
                          <img
                            src={scene.thumbnail_url}
                            alt={scene.scene_title}
                            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                            loading="lazy"
                            onError={(e) => {
                              (e.target as HTMLImageElement).src = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='225' viewBox='0 0 400 225'%3E%3Crect width='400' height='225' fill='%2318181b'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%2371717a' font-size='14' font-family='sans-serif'%3E🎬 Phân Cảnh Phim%3C/text%3E%3C/svg%3E";
                            }}
                          />
                          <div className="absolute top-2 left-2 flex items-center gap-1.5">
                            <Badge className="bg-black/80 text-white font-mono text-[10px] px-2 py-0.5 border border-white/20">
                              #{scene.moment_index || sIdx + 1}
                            </Badge>
                            <Badge className={`text-[9px] font-bold px-1.5 py-0 border ${highlightColor}`}>
                              {scene.highlight_type?.toUpperCase() || "SCENE"}
                            </Badge>
                          </div>

                          <div className="absolute bottom-2 right-2">
                            <Badge className="bg-black/90 text-amber-300 font-mono text-[10px] px-2 py-0.5 border border-amber-500/30">
                              ⏱️ {scene.start_time?.toFixed(1)}s - {scene.end_time?.toFixed(1)}s
                            </Badge>
                          </div>
                        </div>

                        {/* Content & Metadata */}
                        <div className="p-3.5 space-y-2 flex-1 flex flex-col justify-between">
                          <div className="space-y-1.5">
                            <h4 className="font-bold text-xs text-white group-hover:text-purple-300 transition-colors line-clamp-1">
                              {scene.scene_title || `Phân Cảnh #${sIdx + 1}`}
                            </h4>

                            {scene.srt_dialogue && (
                              <p className="text-[11px] text-zinc-300 italic bg-black/40 p-2 rounded-lg border border-zinc-800/80 line-clamp-2">
                                💬 "{scene.srt_dialogue}"
                              </p>
                            )}

                            <p className="text-[11px] text-zinc-400 line-clamp-3 leading-relaxed">
                              {scene.visual_description}
                            </p>
                          </div>

                          {/* Tags & Action */}
                          <div className="pt-2 border-t border-zinc-800/60 flex items-center justify-between gap-2">
                            <div className="flex flex-wrap gap-1 max-w-[180px] overflow-hidden">
                              {scene.tags?.slice(0, 2).map((t, tIdx) => (
                                <span key={tIdx} className="text-[9px] font-mono text-zinc-400 bg-zinc-800 px-1.5 py-0.5 rounded">
                                  #{t}
                                </span>
                              ))}
                            </div>

                            <a
                              href={scene.thumbnail_url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-[10px] text-purple-400 hover:text-purple-300 font-bold flex items-center gap-1"
                            >
                              <Eye className="w-3 h-3" /> Xem Ảnh
                            </a>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: NOVEL CHAPTERS EXPLORER */}
      {activeTab === "chapters" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          {/* Left Column: Chapters Search & List (4 cols) */}
          <div className="lg:col-span-4 space-y-4">
            <div className="p-3.5 rounded-2xl bg-zinc-900/80 border border-zinc-800 space-y-3 shadow-md">
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <Input
                  type="text"
                  value={chapterSearch}
                  onChange={(e) => setChapterSearch(e.target.value)}
                  placeholder="Tìm theo số chương hoặc từ khóa (vd: 682, Nam Lũng)..."
                  className="pl-8 bg-black/60 border-zinc-700 text-xs h-8 rounded-lg"
                />
              </div>

              <div className="text-[11px] text-zinc-400 flex items-center justify-between">
                <span>Hiển thị {filteredChapters.length} / {chapters.length} chương</span>
                {isLoadingChapters && <span className="text-blue-400 animate-pulse">Đang tải...</span>}
              </div>

              <div className="space-y-1 max-h-[520px] overflow-y-auto pr-1">
                {filteredChapters.map((ch) => (
                  <div
                    key={ch.filename}
                    onClick={() => loadChapterContent(selectedNovel.id, ch.filename)}
                    className={`p-2 rounded-lg border text-xs cursor-pointer transition-all flex items-center justify-between ${
                      selectedChapterFilename === ch.filename
                        ? "bg-blue-500/20 border-blue-500/50 text-blue-300 font-bold"
                        : "bg-black/40 border-zinc-800 text-zinc-300 hover:border-zinc-700"
                    }`}
                  >
                    <span className="truncate">{ch.title}</span>
                    <span className="text-[10px] text-zinc-500 font-mono shrink-0">{ch.size_kb || 0} KB</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right Column: Chapter Content Reader (8 cols) */}
          <div className="lg:col-span-8 space-y-4">
            <div className="p-4 rounded-2xl bg-zinc-900/80 border border-zinc-800 space-y-3 shadow-lg">
              <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
                <h3 className="text-xs font-bold text-blue-300 truncate">
                  📄 {selectedChapterFilename || "Chương truyện nguyên tác"}
                </h3>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    navigator.clipboard.writeText(chapterContent);
                    toast.success("Đã sao chép nguyên tác chương!");
                  }}
                  className="border-zinc-700 bg-zinc-800 text-zinc-200 text-xs h-8 gap-1.5 rounded-xl"
                >
                  <Copy className="w-3.5 h-3.5" />
                  Sao Chép
                </Button>
              </div>

              <textarea
                value={chapterContent}
                readOnly
                rows={22}
                className="w-full p-4 rounded-xl bg-black/90 border border-zinc-800 font-mono text-xs text-zinc-300 leading-relaxed outline-none resize-y"
                style={{ minHeight: "520px" }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Novel Import Modal */}
      <NovelImportModal
        open={isNovelModalOpen}
        onOpenChange={setIsNovelModalOpen}
        selectedNovelId={selectedNovel?.id || "Pham nhan tu tien"}
        onSelectNovel={(novel) => {
          setSelectedNovel(novel);
          loadNovels();
          loadScripts(novel.id);
          loadChapters(novel.id);
          loadAnalyzedScenesList(novel.id);
        }}
      />

      {/* Google Drive Config Modal */}
      {driveConfigOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 max-w-md w-full space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <h3 className="font-bold text-sm text-white flex items-center gap-2">
                <Cloud className="w-4 h-4 text-blue-400" /> Cấu Hình Google Drive API
              </h3>
              <button
                onClick={() => setDriveConfigOpen(false)}
                className="text-zinc-500 hover:text-white text-xs"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="space-y-1">
                <span className="text-zinc-400 font-semibold">Client ID (Google OAuth 2.0):</span>
                <Input
                  type="text"
                  value={driveConfig.client_id || ""}
                  onChange={(e) => setDriveConfig({ ...driveConfig, client_id: e.target.value })}
                  placeholder="apps.googleusercontent.com"
                  className="bg-black/60 border-zinc-700 text-xs h-8"
                />
              </div>

              <div className="space-y-1">
                <span className="text-zinc-400 font-semibold">Client Secret:</span>
                <Input
                  type="password"
                  value={driveConfig.client_secret || ""}
                  onChange={(e) => setDriveConfig({ ...driveConfig, client_secret: e.target.value })}
                  placeholder="GOCSPX-..."
                  className="bg-black/60 border-zinc-700 text-xs h-8"
                />
              </div>

              <div className="space-y-1">
                <span className="text-zinc-400 font-semibold">Refresh Token / Access Token:</span>
                <Input
                  type="password"
                  value={driveConfig.refresh_token || ""}
                  onChange={(e) => setDriveConfig({ ...driveConfig, refresh_token: e.target.value })}
                  placeholder="1//0e..."
                  className="bg-black/60 border-zinc-700 text-xs h-8"
                />
              </div>

              <div className="space-y-1">
                <span className="text-zinc-400 font-semibold">ID Thư Mục Drive Đích (Tùy chọn):</span>
                <Input
                  type="text"
                  value={driveConfig.target_folder_id || ""}
                  onChange={(e) => setDriveConfig({ ...driveConfig, target_folder_id: e.target.value })}
                  placeholder="Để trống để tự động tạo thư mục CapCut_Scenes_Dataset"
                  className="bg-black/60 border-zinc-700 text-xs h-8"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-zinc-800">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setDriveConfigOpen(false)}
                className="text-xs h-8 border-zinc-700 text-zinc-300"
              >
                Hủy
              </Button>
              <Button
                type="button"
                size="sm"
                onClick={handleSaveDriveConfig}
                className="bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs h-8 px-4 shadow-sm"
              >
                Lưu Cấu Hình
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
