import React, { useState } from "react";
import { toast } from "sonner";
import {
  Globe,
  Sparkles,
  Volume2,
  Play,
  Languages,
  Zap,
  Shield,
} from "lucide-react";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "./ui/dialog";
import { Badge } from "./ui/badge";
import { Input } from "./ui/input";
import {
  fetchProjectConfig,
  saveProjectConfig,
  runProjectPipeline,
} from "../lib/api";

export interface LanguageDef {
  code: string;
  name: string;
  nativeName: string;
  flag: string;
  targetLangName: string;
  sourceLangName: string;
  voiceName?: string;
}

export const SUPPORTED_LANGUAGES: LanguageDef[] = [
  { code: "vi", name: "Tiếng Việt", nativeName: "Tiếng Việt", flag: "🇻🇳", targetLangName: "Vietnamese", sourceLangName: "Vietnamese" },
  { code: "en", name: "Tiếng Anh", nativeName: "English", flag: "🇺🇸", targetLangName: "English", sourceLangName: "English" },
  { code: "zh", name: "Tiếng Trung", nativeName: "中文", flag: "🇨🇳", targetLangName: "Chinese", sourceLangName: "Chinese" },
  { code: "ja", name: "Tiếng Nhật", nativeName: "日本語", flag: "🇯🇵", targetLangName: "Japanese", sourceLangName: "Japanese" },
  { code: "ko", name: "Tiếng Hàn", nativeName: "한국어", flag: "🇰🇷", targetLangName: "Korean", sourceLangName: "Korean" },
  { code: "th", name: "Tiếng Thái", nativeName: "ภาษาไทย", flag: "🇹🇭", targetLangName: "Thai", sourceLangName: "Thai" },
  { code: "id", name: "Tiếng Indonesia", nativeName: "Bahasa Indonesia", flag: "🇮🇩", targetLangName: "Indonesian", sourceLangName: "Indonesian" },
  { code: "es", name: "Tây Ban Nha", nativeName: "Español", flag: "🇪🇸", targetLangName: "Spanish", sourceLangName: "Spanish" },
  { code: "fr", name: "Tiếng Pháp", nativeName: "Français", flag: "🇫🇷", targetLangName: "French", sourceLangName: "French" },
  { code: "de", name: "Tiếng Đức", nativeName: "Deutsch", flag: "🇩🇪", targetLangName: "German", sourceLangName: "German" },
  { code: "ru", name: "Tiếng Nga", nativeName: "Русский", flag: "🇷🇺", targetLangName: "Russian", sourceLangName: "Russian" },
  { code: "pt", name: "Bồ Đào Nha", nativeName: "Português", flag: "🇧🇷", targetLangName: "Portuguese", sourceLangName: "Portuguese" },
];

interface MultiLangTranslateModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  folder: string;
  currentConfig?: any;
  onSuccess?: () => void;
}

export const MultiLangTranslateModal: React.FC<MultiLangTranslateModalProps> = ({
  open,
  onOpenChange,
  folder,
  currentConfig,
  onSuccess,
}) => {
  const [selectedTargetLangs, setSelectedTargetLangs] = useState<string[]>(["Vietnamese"]);
  const [sourceLang, setSourceLang] = useState<string>("Chinese");
  const [translationMethod, setTranslationMethod] = useState<string>("ai");
  const [enableTTS, setEnableTTS] = useState<boolean>(true);
  const [ttsSpeed, setTtsSpeed] = useState<number>(1.15);
  const [autoBlurSub, setAutoBlurSub] = useState<boolean>(true);
  const [antiCopyright, setAntiCopyright] = useState<boolean>(true);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const handleToggleLang = (langName: string) => {
    if (selectedTargetLangs.includes(langName)) {
      if (selectedTargetLangs.length === 1) {
        toast.info("Vui lòng giữ lại ít nhất 1 ngôn ngữ!");
        return;
      }
      setSelectedTargetLangs(selectedTargetLangs.filter((l) => l !== langName));
    } else {
      setSelectedTargetLangs([...selectedTargetLangs, langName]);
    }
  };

  const handleSelectAll = () => {
    if (selectedTargetLangs.length === SUPPORTED_LANGUAGES.length) {
      setSelectedTargetLangs(["Vietnamese"]);
    } else {
      setSelectedTargetLangs(SUPPORTED_LANGUAGES.map((l) => l.targetLangName));
    }
  };

  const isAllSelected = selectedTargetLangs.length === SUPPORTED_LANGUAGES.length;

  const handleStartTranslate = async () => {
    if (!folder) {
      toast.error("Chưa chọn thư mục dự án!");
      return;
    }

    if (selectedTargetLangs.length === 0) {
      toast.error("Vui lòng chọn ít nhất 1 ngôn ngữ đích!");
      return;
    }

    setIsSubmitting(true);
    try {
      let cfg = currentConfig;
      if (!cfg || Object.keys(cfg).length === 0) {
        cfg = await fetchProjectConfig(folder);
      }

      for (const targetLang of selectedTargetLangs) {
        const updatedConfig = {
          ...cfg,
          source_language: sourceLang,
          target_language: targetLang,
          target_languages: selectedTargetLangs,
          translation_method: translationMethod,
          hardsub_blur_enabled: autoBlurSub,
          enable_anti_copyright: antiCopyright,
          tts_speed: ttsSpeed,
          tts_engine: enableTTS ? "local" : "none",
          use_local_whisper: true,
        };

        await saveProjectConfig(folder, updatedConfig);
        await runProjectPipeline(folder);
      }

      if (selectedTargetLangs.length === 1) {
        const langObj = SUPPORTED_LANGUAGES.find((l) => l.targetLangName === selectedTargetLangs[0]);
        toast.success(
          `🚀 Đã bắt đầu dịch video sang ${langObj?.flag || "🌐"} ${langObj?.name || selectedTargetLangs[0]}!`,
          {
            description: `Dự án "${folder}" đã được đưa vào hàng chờ xử lý AI & Render CapCut.`,
          }
        );
      } else {
        toast.success(
          `🚀 Đã khởi chạy Dịch Toàn Bộ ${selectedTargetLangs.length} Ngôn Ngữ Thành Công!`,
          {
            description: `Hệ thống đang tự động bóc tách âm thanh và render trọn bộ ${selectedTargetLangs.length} phiên bản video.`,
          }
        );
      }

      onOpenChange(false);
      if (onSuccess) onSuccess();
    } catch (err: any) {
      toast.error("Lỗi dịch video", { description: err.message || String(err) });
    } finally {
      setIsSubmitting(false);
    }
  };

  const singleLang = selectedTargetLangs.length === 1
    ? SUPPORTED_LANGUAGES.find((l) => l.targetLangName === selectedTargetLangs[0])
    : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-zinc-950 border-zinc-800 text-zinc-100 max-w-2xl p-6 shadow-2xl rounded-2xl">
        <DialogHeader className="space-y-1">
          <div className="flex items-center justify-between">
            <DialogTitle className="text-base font-extrabold text-white flex items-center gap-2">
              <span className="p-1.5 rounded-lg bg-gradient-to-tr from-amber-500 to-purple-600 text-white">
                <Languages className="w-4 h-4" />
              </span>
              Dịch Đa Ngôn Ngữ & Lồng Tiếng AI (Multi-Language Studio)
            </DialogTitle>
            <Badge variant="outline" className="border-purple-500/40 text-purple-400 bg-purple-500/10 text-[11px]">
              Dự án: {folder || "default"}
            </Badge>
          </div>
          <DialogDescription className="text-xs text-zinc-400">
            Tự động nhận diện giọng nói (Whisper), dịch ngữ cảnh AI (Gemini/GPT), xóa phụ đề gốc & lồng tiếng AI chất lượng cao.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Language Selection Grid */}
          <div className="space-y-2">
            <div className="text-xs font-bold text-zinc-200 flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <Globe className="w-3.5 h-3.5 text-blue-400" /> Chọn Ngôn Ngữ Đích ({selectedTargetLangs.length}/{SUPPORTED_LANGUAGES.length}):
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleSelectAll}
                className="h-6 text-[11px] px-2.5 border-purple-500/40 bg-purple-500/10 text-purple-300 hover:bg-purple-500/20 font-bold"
              >
                {isAllSelected ? "🔄 Đặt lại (Chỉ Tiếng Việt)" : "✨ Chọn Tất Cả 12 Ngôn Ngữ"}
              </Button>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {SUPPORTED_LANGUAGES.map((lang) => {
                const isSelected = selectedTargetLangs.includes(lang.targetLangName);
                return (
                  <div
                    key={lang.code}
                    onClick={() => handleToggleLang(lang.targetLangName)}
                    className={`p-2.5 rounded-xl border cursor-pointer transition-all flex items-center gap-2.5 ${
                      isSelected
                        ? "bg-[#622FF6]/25 border-[#622FF6] text-white font-bold shadow-md shadow-[#622FF6]/25 scale-[1.02]"
                        : "bg-zinc-900/60 border-zinc-800 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700"
                    }`}
                  >
                    <span className="text-xl shrink-0">{lang.flag}</span>
                    <div className="min-w-0 leading-tight">
                      <div className="text-xs font-bold truncate">{lang.name}</div>
                      <div className="text-[10px] text-zinc-500 truncate">{lang.nativeName}</div>
                    </div>
                    {isSelected && (
                      <span className="ml-auto flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-[#622FF6] text-[10px] text-white font-black">
                        ✓
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Engine & Settings Options */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
            {/* Left: Source Language & Translation Engine */}
            <div className="p-3.5 rounded-xl bg-zinc-900/50 border border-zinc-800/80 space-y-3">
              <div className="text-xs font-bold text-zinc-300 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-amber-400" /> Cấu hình Dịch Thuật
              </div>

              <div className="space-y-1">
                <label className="text-[11px] text-zinc-400">Ngôn ngữ nguồn video:</label>
                <select
                  value={sourceLang}
                  onChange={(e) => setSourceLang(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-200 font-medium"
                >
                  <option value="Chinese">🇨🇳 Tiếng Trung (Douyin / Kuaishou / Bilibili)</option>
                  <option value="English">🇺🇸 Tiếng Anh (YouTube / TikTok / Reels)</option>
                  <option value="Japanese">🇯🇵 Tiếng Nhật (Anime / Vlog)</option>
                  <option value="Korean">🇰🇷 Tiếng Hàn (K-Drama / K-Pop)</option>
                  <option value="Vietnamese">🇻🇳 Tiếng Việt</option>
                  <option value="auto">🌐 Tự động nhận diện (Auto Detect)</option>
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-[11px] text-zinc-400">Động cơ AI Dịch:</label>
                <select
                  value={translationMethod}
                  onChange={(e) => setTranslationMethod(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-200 font-medium"
                >
                  <option value="ai">🤖 AI Chuyên Sâu (Gemini / GPT / Gemma - Giữ ngữ cảnh)</option>
                  <option value="google">⚡ Google Translate (Miễn phí & Tốc độ cao)</option>
                </select>
              </div>
            </div>

            {/* Right: Voiceover TTS & Video Enhancements */}
            <div className="p-3.5 rounded-xl bg-zinc-900/50 border border-zinc-800/80 space-y-3">
              <div className="text-xs font-bold text-zinc-300 flex items-center gap-1.5">
                <Volume2 className="w-3.5 h-3.5 text-emerald-400" /> Lồng Tiếng & Xử Lý Video
              </div>

              <div className="space-y-2">
                <label className="flex items-center justify-between text-xs text-zinc-300 cursor-pointer">
                  <span className="flex items-center gap-1.5">
                    <Volume2 className="w-3.5 h-3.5 text-emerald-400" /> Lồng tiếng AI (TTS)
                  </span>
                  <input
                    type="checkbox"
                    checked={enableTTS}
                    onChange={(e) => setEnableTTS(e.target.checked)}
                    className="rounded border-zinc-700 bg-zinc-950 text-[#622FF6]"
                  />
                </label>

                {enableTTS && (
                  <div className="flex items-center justify-between text-[11px] text-zinc-400">
                    <span>Tốc độ giọng đọc:</span>
                    <div className="flex items-center gap-1.5">
                      <Input
                        type="number"
                        step="0.05"
                        min="0.8"
                        max="2.0"
                        value={ttsSpeed}
                        onChange={(e) => setTtsSpeed(parseFloat(e.target.value) || 1.15)}
                        className="w-16 h-7 bg-zinc-950 border-zinc-800 text-xs text-center py-0"
                      />
                      <span className="text-zinc-500">x</span>
                    </div>
                  </div>
                )}

                <label className="flex items-center justify-between text-xs text-zinc-300 cursor-pointer pt-1">
                  <span className="flex items-center gap-1.5">
                    <Zap className="w-3.5 h-3.5 text-purple-400" /> Tự động xóa phụ đề gốc (Blur Hardsub)
                  </span>
                  <input
                    type="checkbox"
                    checked={autoBlurSub}
                    onChange={(e) => setAutoBlurSub(e.target.checked)}
                    className="rounded border-zinc-700 bg-zinc-950 text-[#622FF6]"
                  />
                </label>

                <label className="flex items-center justify-between text-xs text-zinc-300 cursor-pointer">
                  <span className="flex items-center gap-1.5">
                    <Shield className="w-3.5 h-3.5 text-cyan-400" /> Lách bản quyền động (Smart Defense)
                  </span>
                  <input
                    type="checkbox"
                    checked={antiCopyright}
                    onChange={(e) => setAntiCopyright(e.target.checked)}
                    className="rounded border-zinc-700 bg-zinc-950 text-[#622FF6]"
                  />
                </label>
              </div>
            </div>
          </div>
        </div>

        <DialogFooter className="pt-3 border-t border-zinc-800/80 flex items-center justify-between">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
            className="border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 text-xs h-9"
          >
            Hủy
          </Button>

          <Button
            size="sm"
            onClick={handleStartTranslate}
            disabled={isSubmitting}
            className="bg-gradient-to-r from-amber-500 via-purple-600 to-[#622FF6] hover:opacity-90 text-white font-bold text-xs h-9 px-4 gap-2 shadow-lg shadow-purple-500/20"
          >
            <Play className={`w-3.5 h-3.5 fill-white ${isSubmitting ? "animate-spin" : ""}`} />
            {isAllSelected
              ? "🚀 Dịch Ra Toàn Bộ 12 Ngôn Ngữ Cùng Lúc (Batch All)"
              : singleLang
              ? `Bắt Đầu Dịch Sang ${singleLang.flag} ${singleLang.name}`
              : `Dịch Sang ${selectedTargetLangs.length} Ngôn Ngữ Đã Chọn`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
