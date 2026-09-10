import React, { useState, useMemo, useRef } from "react";
import {
  Film, Sparkles, RefreshCw, Copy, Trash2, Search,
  Maximize2, Minimize2, Clock, Plus, X, AlignLeft,
  MapPin, Users, Image as ImageIcon, ChevronDown, ChevronUp
} from "lucide-react";
import { Button } from "./ui/button";
import { toast } from "sonner";

export interface ScriptReaderEditorProps {
  value: string;
  onChange: (val: string) => void;
  onGenerateAI?: () => void;
  generating?: boolean;
  onClear?: () => void;
  ttsSpeed?: number;
  novelTitle?: string;
}

interface SceneItem {
  id: string;
  sceneIndex: number;
  text: string;
}

interface SceneMeta {
  title?: string;
  location?: string;
  characters?: string[];
  action_summary?: string;
  visual_prompt?: string;
}

export const ScriptReaderEditor: React.FC<ScriptReaderEditorProps> = ({
  value,
  onChange,
  onGenerateAI,
  generating = false,
  onClear,
  ttsSpeed = 1.2,
  novelTitle = "Phàm Nhân Tu Tiên",
}) => {
  // Mode: "scenes" (biên tập theo từng phân cảnh) | "document" (văn bản liền mạch)
  const [mode, setMode] = useState<"scenes" | "document">("scenes");
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [analyzingScenes, setAnalyzingScenes] = useState<boolean>(false);

  // Lưu trữ metadata phân cảnh sinh từ AI (tiêu đề, địa điểm, nhân vật, visual prompt)
  const [sceneMetaMap, setSceneMetaMap] = useState<{ [index: number]: SceneMeta }>({});
  const [expandedVisuals, setExpandedVisuals] = useState<{ [index: number]: boolean }>({});

  // Search & Replace
  const [showSearch, setShowSearch] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [replaceQuery, setReplaceQuery] = useState<string>("");

  // Auto-resize textareas ref map
  const textareaRefs = useRef<{ [key: string]: HTMLTextAreaElement | null }>({});

  // 1. TÁCH VĂN BẢN THÀNH CÁC PHÂN CẢNH (Dựa vào thẻ ngắt cảnh [0.5] hoặc [0.4]+)
  const scenes: SceneItem[] = useMemo(() => {
    if (!value || !value.trim()) {
      return [{ id: "scene_1", sceneIndex: 1, text: "" }];
    }

    // Tách theo các thẻ chuyển cảnh [0.4], [0.5], [0.8], [1.0]...
    const rawChunks = value.split(/(?:^|\n)\[(?:0\.[4-9]|\d+(?:\.\d+)?)\](?:\n|$)/);
    const parsed: SceneItem[] = [];

    rawChunks.forEach((chunk, i) => {
      const trimmed = chunk.trim();
      if (trimmed || rawChunks.length === 1) {
        parsed.push({
          id: `scene_${i + 1}`,
          sceneIndex: parsed.length + 1,
          text: trimmed,
        });
      }
    });

    return parsed.length > 0 ? parsed : [{ id: "scene_1", sceneIndex: 1, text: "" }];
  }, [value]);

  // Cập nhật lại toàn văn bản khi sửa một phân cảnh
  const handleSceneTextChange = (index: number, newText: string) => {
    const updated = [...scenes];
    updated[index].text = newText;
    const combined = updated.map((s) => s.text.trim()).filter(Boolean).join("\n[0.5]\n");
    onChange(combined);
  };

  // Cập nhật tiêu đề cảnh
  const handleSceneTitleChange = (index: number, newTitle: string) => {
    setSceneMetaMap((prev) => ({
      ...prev,
      [index]: {
        ...prev[index],
        title: newTitle,
      },
    }));
  };

  // Cập nhật visual prompt của cảnh
  const handleScenePromptChange = (index: number, newPrompt: string) => {
    setSceneMetaMap((prev) => ({
      ...prev,
      [index]: {
        ...prev[index],
        visual_prompt: newPrompt,
      },
    }));
  };

  // GỌI BỘ ÓC AI PHÂN TÍCH THÀNH CÁC PHÂN CẢNH ĐIỆN ẢNH (KHÔNG PHẢI MỖI CÂU 1 CẢNH)
  const handleAnalyzeScenesWithAI = async () => {
    if (!value || !value.trim()) {
      toast.error("Chưa có nội dung kịch bản để phân tích phân cảnh!");
      return;
    }

    setAnalyzingScenes(true);
    toast.info("🎬 Đạo diễn AI đang đọc hiểu kịch bản & phân chia phân cảnh điện ảnh...", {
      description: "Gom nhóm theo bối cảnh, nhân vật và tạo visual prompt cho từng cảnh (~20-35s)...",
    });

    try {
      const res = await fetch("/api/novel/analyze_scenes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          script_text: value,
          novel_title: novelTitle,
        }),
      });
      const data = await res.json();
      if (data.success && Array.isArray(data.scenes) && data.scenes.length > 0) {
        const newMeta: { [idx: number]: SceneMeta } = {};
        data.scenes.forEach((sc: any, i: number) => {
          newMeta[i] = {
            title: sc.title,
            location: sc.location,
            characters: sc.characters,
            action_summary: sc.action_summary,
            visual_prompt: sc.visual_prompt,
          };
        });
        setSceneMetaMap(newMeta);

        if (data.full_plain_text) {
          onChange(data.full_plain_text);
        }
        setMode("scenes");
        toast.success(`🎉 Đã phân tích thành công ${data.scenes.length} phân cảnh điện ảnh!`, {
          description: "Mỗi phân cảnh gồm khối lời thoại mạch lạc khớp với 1 khung hình trên timeline CapCut.",
        });
      } else {
        toast.error("Không thể phân tích phân cảnh", { description: data.error || "Lỗi server" });
      }
    } catch (err: any) {
      toast.error("Lỗi kết nối AI phân cảnh", { description: err.message });
    } finally {
      setAnalyzingScenes(false);
    }
  };

  // Tách phân cảnh ngay tại vị trí con trỏ hoặc thêm phân cảnh mới bên dưới
  const handleAddSceneAfter = (index: number) => {
    const updated = [...scenes];
    updated.splice(index + 1, 0, {
      id: `scene_${Date.now()}`,
      sceneIndex: index + 2,
      text: "",
    });
    const combined = updated.map((s) => s.text.trim()).filter(Boolean).join("\n[0.5]\n");
    onChange(combined);
    toast.success(`Đã thêm Phân Cảnh #${index + 2}`);
  };

  // Hợp nhất phân cảnh hiện tại với phân cảnh trước đó
  const handleMergeWithPrev = (index: number) => {
    if (index === 0) return;
    const updated = [...scenes];
    const prevText = updated[index - 1].text.trim();
    const curText = updated[index].text.trim();
    updated[index - 1].text = prevText ? `${prevText}\n[0.2]\n${curText}` : curText;
    updated.splice(index, 1);
    const combined = updated.map((s) => s.text.trim()).filter(Boolean).join("\n[0.5]\n");
    onChange(combined);
    toast.info(`Đã gộp Cảnh #${index + 1} vào Cảnh #${index}`);
  };

  // Xóa một phân cảnh
  const handleDeleteScene = (index: number) => {
    if (scenes.length <= 1) {
      onChange("");
      return;
    }
    const updated = scenes.filter((_, i) => i !== index);
    const combined = updated.map((s) => s.text.trim()).filter(Boolean).join("\n[0.5]\n");
    onChange(combined);
    toast.info(`Đã xóa Phân Cảnh #${index + 1}`);
  };

  // Tự động căn chỉnh chiều cao textarea theo nội dung
  const adjustHeight = (el: HTMLTextAreaElement | null) => {
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.max(68, el.scrollHeight)}px`;
    }
  };

  // Tính toán thống kê nhanh
  const stats = useMemo(() => {
    const textOnly = value.replace(/\[\d+(?:\.\d+)?\]/g, " ");
    const words = textOnly.split(/\s+/).filter(Boolean).length;
    const validScenesCount = scenes.filter((s) => s.text.trim()).length || 1;
    
    // Tốc độ 1.2x: ~200 từ/phút (3.3 từ/giây) + thời gian nghỉ ngắt cảnh
    const effectiveSpeed = Math.max(0.8, Math.min(2.0, ttsSpeed));
    const speechSec = words / ((175 / 60) * effectiveSpeed);
    const pauseSec = validScenesCount * 0.5 + (words * 0.05);
    const totalSec = Math.round(speechSec + pauseSec);

    const mins = Math.floor(totalSec / 60);
    const secs = totalSec % 60;

    return {
      words,
      scenesCount: validScenesCount,
      durationText: `${mins}p ${secs.toString().padStart(2, "0")}s`,
    };
  }, [value, scenes, ttsSpeed]);

  // Tìm & Thay thế
  const handleReplaceAll = () => {
    if (!searchQuery) {
      toast.error("Vui lòng nhập từ cần tìm!");
      return;
    }
    const regex = new RegExp(searchQuery.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
    const matches = value.match(regex);
    if (!matches || matches.length === 0) {
      toast.info(`Không tìm thấy "${searchQuery}" trong kịch bản.`);
      return;
    }
    const count = matches.length;
    const updated = value.replace(regex, replaceQuery);
    onChange(updated);
    toast.success(`Đã thay thế ${count} vị trí "${searchQuery}" ➔ "${replaceQuery}"!`);
    setSearchQuery("");
    setReplaceQuery("");
    setShowSearch(false);
  };

  return (
    <div
      className={`rounded-2xl border border-amber-500/40 bg-zinc-950/95 transition-all flex flex-col shadow-xl ${
        isFullscreen
          ? "fixed inset-2 z-50 p-5 bg-zinc-950/98 shadow-2xl backdrop-blur-lg overflow-hidden"
          : "p-4 space-y-3"
      }`}
    >
      {/* 1. THANH ĐIỀU KHIỂN TINH GỌN (CLEAN & MINIMAL TOOLBAR) */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-zinc-800 pb-3">
        <div className="flex items-center gap-2.5 flex-wrap">
          {/* TABS CHUYỂN ĐỔI CHẾ ĐỘ: PHÂN CẢNH vs TOÀN VĂN */}
          <div className="flex items-center p-1 rounded-xl bg-zinc-900 border border-zinc-800 shadow-inner">
            <button
              type="button"
              onClick={() => setMode("scenes")}
              className={`px-3.5 py-1.5 text-xs font-bold rounded-lg transition-all flex items-center gap-2 ${
                mode === "scenes"
                  ? "bg-amber-500 text-zinc-950 shadow-sm"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <Film className="w-3.5 h-3.5" />
              <span>Theo Phân Cảnh ({stats.scenesCount} cảnh)</span>
            </button>
            <button
              type="button"
              onClick={() => setMode("document")}
              className={`px-3.5 py-1.5 text-xs font-bold rounded-lg transition-all flex items-center gap-2 ${
                mode === "document"
                  ? "bg-amber-500 text-zinc-950 shadow-sm"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <AlignLeft className="w-3.5 h-3.5" />
              <span>Toàn Văn Liền Mạch (.txt)</span>
            </button>
          </div>

          {/* BADGE THỐNG KÊ NHANH */}
          <div className="flex items-center gap-2 text-xs font-mono">
            <span className="text-zinc-400 flex items-center gap-1 bg-zinc-900/80 px-2 py-1 rounded-lg border border-zinc-800">
              <Clock className="w-3 h-3 text-amber-400" />
              <strong className="text-amber-300">~{stats.durationText}</strong>
              <span className="text-[10px] text-zinc-500">({ttsSpeed}x)</span>
            </span>
            <span className="text-zinc-400 bg-zinc-900/80 px-2 py-1 rounded-lg border border-zinc-800 hidden md:inline">
              {stats.words} từ
            </span>
          </div>
        </div>

        {/* CÁC NÚT HÀNH ĐỘNG CHÍNH */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {/* NÚT AI PHÂN TÍCH PHÂN CẢNH (CHỦ LỰC) */}
          <Button
            type="button"
            size="sm"
            disabled={analyzingScenes || !value.trim()}
            onClick={handleAnalyzeScenesWithAI}
            className="bg-gradient-to-r from-cyan-600 via-cyan-500 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold text-xs h-8 px-3.5 gap-1.5 rounded-xl shadow-sm border border-cyan-400/40"
            title="Dùng AI phân tích kịch bản thành các phân cảnh điện ảnh chuẩn (không phải mỗi câu 1 cảnh)"
          >
            {analyzingScenes ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-cyan-200" />
                <span>Đang Phân Tích Cảnh...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-3.5 h-3.5 text-cyan-200" />
                <span>✨ AI Phân Tích Phân Cảnh</span>
              </>
            )}
          </Button>

          {onGenerateAI && (
            <Button
              type="button"
              size="sm"
              disabled={generating}
              onClick={onGenerateAI}
              className="bg-amber-500 hover:bg-amber-600 text-zinc-950 font-bold text-xs h-8 px-3.5 gap-1.5 rounded-xl shadow-sm"
            >
              {generating ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  Đang Tạo...
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5" />
                  Sinh Kịch Bản AI
                </>
              )}
            </Button>
          )}

          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => setShowSearch(!showSearch)}
            className={`h-8 px-2.5 text-xs gap-1.5 border rounded-xl ${
              showSearch
                ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                : "text-zinc-300 hover:text-white hover:bg-zinc-800 border-zinc-800"
            }`}
            title="Tìm & thay thế tên nhân vật/từ ngữ"
          >
            <Search className="w-3.5 h-3.5 text-amber-400" />
            <span className="hidden sm:inline">Tìm & Đổi Tên</span>
          </Button>

          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => {
              if (!value.trim()) return toast.error("Chưa có nội dung để sao chép");
              navigator.clipboard.writeText(value);
              toast.success("Đã sao chép toàn bộ kịch bản!");
            }}
            className="h-8 px-2.5 text-xs text-zinc-300 hover:text-white hover:bg-zinc-800 border border-zinc-800 rounded-xl"
            title="Sao chép toàn văn"
          >
            <Copy className="w-3.5 h-3.5" />
          </Button>

          {onClear && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={onClear}
              className="h-8 px-2.5 text-xs text-zinc-500 hover:text-red-400 hover:bg-zinc-900 border border-zinc-800 rounded-xl"
              title="Xóa toàn bộ"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </Button>
          )}

          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="h-8 px-2.5 text-xs text-zinc-300 hover:text-amber-400 hover:bg-zinc-800 border border-zinc-800 rounded-xl"
            title={isFullscreen ? "Thu nhỏ lại" : "Mở rộng toàn màn hình để đọc và sửa thoải mái"}
          >
            {isFullscreen ? <Minimize2 className="w-3.5 h-3.5 text-amber-400" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </Button>
        </div>
      </div>

      {/* 2. THANH TÌM & THAY THẾ (NẾU MỞ) */}
      {showSearch && (
        <div className="p-3 rounded-xl bg-zinc-900/90 border border-amber-500/30 flex flex-col sm:flex-row items-center gap-2 animate-in fade-in slide-in-from-top-2">
          <input
            type="text"
            placeholder="Tìm từ (vd: Hàn Lập, Lạc Vân Tông...)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="flex-1 h-8 px-3 rounded-lg bg-zinc-950 border border-zinc-800 text-xs text-zinc-100 outline-none focus:border-amber-400"
          />
          <input
            type="text"
            placeholder="Thay bằng (vd: Hàn lão ma...)"
            value={replaceQuery}
            onChange={(e) => setReplaceQuery(e.target.value)}
            className="flex-1 h-8 px-3 rounded-lg bg-zinc-950 border border-zinc-800 text-xs text-zinc-100 outline-none focus:border-amber-400"
          />
          <div className="flex items-center gap-2">
            <Button
              type="button"
              size="sm"
              onClick={handleReplaceAll}
              className="h-8 px-3 bg-amber-500 hover:bg-amber-600 text-zinc-950 font-bold text-xs rounded-lg"
            >
              Đổi Tất Cả
            </Button>
            <button
              type="button"
              onClick={() => setShowSearch(false)}
              className="p-1.5 text-zinc-500 hover:text-white"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* 3. VÙNG SOẠN THẢO CHÍNH (MAIN EDITOR AREA) */}
      <div className={`flex-1 overflow-y-auto pr-1 custom-scrollbar ${isFullscreen ? "max-w-4xl mx-auto w-full py-3" : "py-1"}`}>
        {mode === "scenes" ? (
          /* ========================================================================= */
          /* CHẾ ĐỘ 1: BIÊN TẬP THEO PHÂN CẢNH (CLICK VÀO GÕ NGAY, KHÔNG CẦN BẤM SỬA)   */
          /* ========================================================================= */
          <div className="space-y-4">
            {scenes.map((scene, idx) => {
              const sceneWordCount = scene.text.replace(/\[\d+(?:\.\d+)?\]/g, " ").split(/\s+/).filter(Boolean).length;
              const sceneSec = Math.round(sceneWordCount / 3.3 + 0.5);
              const meta = sceneMetaMap[idx] || {};
              const isVisualExpanded = !!expandedVisuals[idx];

              return (
                <div key={scene.id} className="space-y-2 group">
                  {/* SCENE CARD */}
                  <div className="rounded-2xl bg-zinc-900/60 border border-zinc-800/90 hover:border-amber-500/50 transition-all p-4 shadow-sm focus-within:border-amber-400 focus-within:ring-1 focus-within:ring-amber-400/30">
                    {/* Header Cảnh */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-2.5 mb-2.5 border-b border-zinc-800/80 gap-2">
                      <div className="flex items-center gap-2 flex-wrap">
                        {/* BADGE SỐ PHÂN CẢNH */}
                        <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-md bg-amber-500/15 border border-amber-500/30 text-amber-300 font-bold text-xs font-mono">
                          <Film className="w-3.5 h-3.5 text-amber-400" />
                          Phân Cảnh #{scene.sceneIndex}
                        </span>

                        {/* TIÊU ĐỀ PHÂN CẢNH (CÓ THỂ SỬA TRỰC TIẾP) */}
                        <input
                          type="text"
                          value={meta.title || `Diễn biến Cảnh #${scene.sceneIndex}`}
                          onChange={(e) => handleSceneTitleChange(idx, e.target.value)}
                          placeholder="Tiêu đề phân cảnh..."
                          className="bg-transparent border-0 text-xs font-semibold text-zinc-200 focus:text-amber-300 focus:outline-none focus:ring-0 px-1 py-0.5 rounded hover:bg-zinc-800/50 transition-colors w-44 sm:w-60 truncate"
                          title="Bấm để đổi tiêu đề cảnh"
                        />

                        {/* CHIP ĐỊA ĐIỂM */}
                        {meta.location && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-cyan-950/40 border border-cyan-800/50 text-cyan-300 text-[11px]">
                            <MapPin className="w-2.5 h-2.5 text-cyan-400" />
                            {meta.location}
                          </span>
                        )}

                        {/* CHIP NHÂN VẬT */}
                        {meta.characters && meta.characters.length > 0 && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-purple-950/40 border border-purple-800/50 text-purple-300 text-[11px] hidden sm:inline-flex">
                            <Users className="w-2.5 h-2.5 text-purple-400" />
                            {meta.characters.join(", ")}
                          </span>
                        )}

                        <span className="text-zinc-500 text-xs font-mono">
                          ~{sceneSec}s • {sceneWordCount} từ
                        </span>
                      </div>

                      {/* Công cụ nhanh của cảnh */}
                      <div className="flex items-center gap-1 text-xs justify-end">
                        {meta.visual_prompt && (
                          <button
                            type="button"
                            onClick={() => setExpandedVisuals((prev) => ({ ...prev, [idx]: !prev[idx] }))}
                            className={`px-2 py-0.5 text-[11px] rounded-md transition-colors flex items-center gap-1 border ${
                              isVisualExpanded
                                ? "bg-cyan-950/60 border-cyan-700/50 text-cyan-300"
                                : "text-zinc-400 hover:text-cyan-300 border-transparent hover:bg-zinc-800"
                            }`}
                            title="Xem chi tiết bối cảnh hình ảnh cho CapCut"
                          >
                            <ImageIcon className="w-3 h-3 text-cyan-400" />
                            <span>Bối cảnh</span>
                            {isVisualExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                          </button>
                        )}
                        {idx > 0 && (
                          <button
                            type="button"
                            onClick={() => handleMergeWithPrev(idx)}
                            className="px-2 py-1 text-[11px] text-zinc-400 hover:text-amber-300 hover:bg-zinc-800 rounded-md transition-colors"
                            title="Gộp cảnh này vào cảnh phía trước"
                          >
                            Gộp vào cảnh trước
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => handleAddSceneAfter(idx)}
                          className="px-2 py-1 text-[11px] text-emerald-400 hover:bg-emerald-950/40 rounded-md transition-colors font-medium"
                          title="Tạo thêm 1 phân cảnh mới bên dưới"
                        >
                          + Thêm cảnh
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteScene(idx)}
                          className="p-1 text-zinc-500 hover:text-red-400 hover:bg-zinc-800 rounded-md transition-colors ml-1"
                          title="Xóa cảnh này"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>

                    {/* KHUNG BỐI CẢNH HÌNH ẢNH (VISUAL PROMPT) NẾU CÓ */}
                    {meta.visual_prompt && isVisualExpanded && (
                      <div className="mb-3 p-2.5 rounded-xl bg-cyan-950/20 border border-cyan-800/30 text-xs space-y-1 animate-in fade-in duration-150">
                        <div className="flex items-center justify-between text-cyan-400 font-semibold text-[11px]">
                          <span className="flex items-center gap-1.5">
                            <ImageIcon className="w-3.5 h-3.5" />
                            🖼️ Mô tả hình ảnh khung hình CapCut (Visual Prompt):
                          </span>
                          <button
                            type="button"
                            onClick={() => {
                              navigator.clipboard.writeText(meta.visual_prompt || "");
                              toast.success("Đã copy visual prompt!");
                            }}
                            className="text-zinc-400 hover:text-white p-0.5"
                            title="Copy prompt"
                          >
                            <Copy className="w-3 h-3" />
                          </button>
                        </div>
                        <input
                          type="text"
                          value={meta.visual_prompt}
                          onChange={(e) => handleScenePromptChange(idx, e.target.value)}
                          className="w-full bg-black/40 border border-cyan-900/40 rounded-lg px-2.5 py-1 text-xs text-cyan-200 font-mono focus:outline-none focus:border-cyan-500"
                        />
                      </div>
                    )}

                    {/* VÙNG NHẬP CHỮ TRỰC TIẾP (CLICK CHUỘT VÀO LÀ GÕ ĐƯỢC NGAY, KHÔNG CẦN NÚT SỬA) */}
                    <textarea
                      ref={(el) => {
                        textareaRefs.current[scene.id] = el;
                        adjustHeight(el);
                      }}
                      value={scene.text}
                      onChange={(e) => {
                        handleSceneTextChange(idx, e.target.value);
                        adjustHeight(e.target);
                      }}
                      rows={3}
                      spellCheck={false}
                      className="w-full bg-transparent text-zinc-100 text-[15px] sm:text-base leading-relaxed outline-none resize-none border-0 p-0 focus:ring-0 font-sans tracking-wide placeholder-zinc-600"
                      placeholder={`Nhập lời thoại thuyết minh cho Phân Cảnh #${scene.sceneIndex}...\n(Một khối bối cảnh gồm 3 đến 7 câu liền mạch, chèn [0.2] để ngắt nghỉ giọng đọc tự nhiên)`}
                    />
                  </div>

                  {/* THANH CHUYỂN PHÂN CẢNH TRỰC QUAN GIỮA CÁC CẢNH */}
                  {idx < scenes.length - 1 && (
                    <div className="flex items-center justify-center py-1 relative">
                      <div className="absolute inset-0 flex items-center">
                        <div className="w-full border-t border-dashed border-zinc-800/80" />
                      </div>
                      <div className="relative flex items-center gap-2 bg-zinc-950 px-3 py-0.5 rounded-full border border-zinc-800 text-[11px] text-zinc-400 font-mono">
                        <span className="text-amber-400/90 font-bold">🎬 [0.5s]</span>
                        <span>Chuyển sang Cảnh #{idx + 2}</span>
                        <button
                          type="button"
                          onClick={() => handleAddSceneAfter(idx)}
                          className="ml-1 text-emerald-400 hover:text-emerald-300 font-bold"
                          title="Chèn thêm 1 cảnh ở giữa"
                        >
                          +
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}

            {/* NÚT THÊM PHÂN CẢNH CUỐI CÙNG */}
            <div className="pt-2 flex justify-center">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => handleAddSceneAfter(scenes.length - 1)}
                className="h-9 px-5 rounded-xl border-dashed border-zinc-700 hover:border-amber-500/50 bg-zinc-900/40 text-zinc-300 hover:text-amber-300 text-xs font-semibold gap-2 shadow-sm"
              >
                <Plus className="w-4 h-4" />
                Thêm Phân Cảnh Tiếp Theo
              </Button>
            </div>
          </div>
        ) : (
          /* ========================================================================= */
          /* CHẾ ĐỘ 2: TOÀN VĂN LIỀN MẠCH (CHO NGƯỜI THÍCH DÁN HOẶC ĐỌC 1 MẠCH DÀI)   */
          /* ========================================================================= */
          <div className="space-y-2">
            <div className="text-xs text-zinc-400 italic flex items-center justify-between px-1">
              <span>
                💡 Chế độ toàn văn .txt: Các phân cảnh được ngăn cách bằng thẻ{" "}
                <strong className="text-amber-400 font-mono">[0.5]</strong> (chuyển cảnh CapCut). Bên trong cảnh dùng{" "}
                <strong className="text-zinc-300 font-mono">[0.2]</strong> để ngắt nghỉ câu thoại.
              </span>
              <span className="font-mono text-amber-300 text-[11px]">
                {stats.words} từ • ~{stats.durationText}
              </span>
            </div>
            <textarea
              value={value}
              onChange={(e) => onChange(e.target.value)}
              rows={isFullscreen ? 22 : 14}
              spellCheck={false}
              className="w-full p-4 rounded-xl bg-zinc-900/80 border border-zinc-800 text-zinc-100 text-[15px] leading-relaxed outline-none focus:border-amber-400 font-sans resize-y custom-scrollbar tracking-wide"
              placeholder="Dán toàn bộ kịch bản thuyết minh vào đây..."
            />
          </div>
        )}
      </div>
    </div>
  );
};
