import React, { useState } from "react";
import { 
  Sparkles, 
  Play, 
  Pause, 
  CheckCircle2, 
  Clock, 
  BookOpen, 
  Tv, 
  Volume2, 
  Layers, 
  Film,
  RefreshCw,
  Plus,
  Trash2,
  Upload,
  Video,
  PlaySquare
} from "lucide-react";
import { Button } from "./ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "./ui/card";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";
import { toast } from "sonner";
import axios from "axios";

interface SceneItem {
  scene_id: number;
  voiceover: string;
  visual_prompt?: string;
  animation?: string;
  duration?: number;
  audio_file?: string;
  image_path?: string;
}

export const NovelStudioPage: React.FC = () => {
  // 1. Novel & Episode Settings
  const [novelName, setNovelName] = useState<string>("xianni");
  const [currentEp, setCurrentEp] = useState<number>(57);
  const [nextEp, setNextEp] = useState<number>(58);

  // 2. Video & Canvas Settings (Không fix cứng)
  const [canvasRatio, setCanvasRatio] = useState<string>("16:9");
  const [videoSpeed, setVideoSpeed] = useState<number>(1.0);
  const [bgmVolume, setBgmVolume] = useState<number>(-16.0);
  const [mediaPaths] = useState<string[]>([]);

  // 3. TTS Voice Settings (Đa dạng giọng đọc & Engine)
  const [ttsEngine, setTtsEngine] = useState<string>("edge-tts");
  const [voice, setVoice] = useState<string>("vi-VN-NamMinhNeural");
  const [ttsSpeed, setTtsSpeed] = useState<number>(1.1);

  // 4. Subtitle & Typography
  const [fontSize, setFontSize] = useState<number>(11.0);
  const [fontColor, setFontColor] = useState<string>("#FFE500");
  const [borderColor, setBorderColor] = useState<string>("#000000");

  // 5. Execution State
  const [loading, setLoading] = useState<boolean>(false);
  const [draftFolder, setDraftFolder] = useState<string | null>(null);
  const [playingScene, setPlayingScene] = useState<number | null>(null);
  const [audioElement, setAudioElement] = useState<HTMLAudioElement | null>(null);

  // 6. Configurable Scenes List
  const [scenes, setScenes] = useState<SceneItem[]>([
    {
      scene_id: 1,
      voiceover: "Ở tập trước, Vương Lâm đã đồ sát toàn tộc họ Đằng, chém đầu Đằng Hóa Nguyên để trả mối huyết hải thâm thù 400 năm. Sang tập 58, Kim Quang Khổng Lồ từ thần thông Cự Ma Tộc giáng xuống, chỉ bằng một phẩy tay đã biến Phác Nam Tử thành tro bụi và nghiền nát cánh tay của sứ giả tu chân quốc cấp bốn, khiến gã sợ mất mật vội bóp nát ngọc giản đào thoát khỏi Triệu quốc.",
      visual_prompt: "Cinematic anime, colossal golden giant in sky waving massive hand...",
      animation: "Zoom Out",
      duration: 18.8
    },
    {
      scene_id: 2,
      voiceover: "Vác theo ngọn tháp đầu lâu ngút trời của tộc Đằng, Vương Lâm bay về ngôi làng nhỏ dưới chân núi Hằng Nhạc năm xưa. Trước ngôi nhà tổ tiên, hắn quỳ rạp rơi lệ dập đầu tạ tội trước linh hồn song thân, trước khi một chưởng đánh tan ngọn tháp đầu lâu thành tro bụi trong gió, chính thức khép lại trang sử hận thù bốn trăm năm.",
      visual_prompt: "Wang Lin kneeling in tears before ancestral village house at sunset...",
      animation: "Zoom In",
      duration: 16.1
    },
    {
      scene_id: 3,
      voiceover: "Trên đường rời đi, Vương Lâm bất ngờ chạm trán một tà dị thanh niên có tu vi cấp bậc Anh Biến Kỳ. Bằng sự quyết đoán và bản lĩnh sinh tử, Vương Lâm dùng tia sét Thiên Kiếp cùng Cấm Phiên với chín mươi chín đạo cấm chế uy hiếp, khiến cường giả thần bí này cũng phải kinh hãi lùi bước mà không dám manh động.",
      visual_prompt: "Wang Lin facing an enigmatic handsome evil youth with multicolored eyes...",
      animation: "Dynamic Shake",
      duration: 15.5
    },
    {
      scene_id: 4,
      voiceover: "Nhận ra Cực Cảnh đã kẹt ở bình cảnh và không thể giúp đột phá Hóa Thần Kỳ, Vương Lâm quyết định để bản tôn Cực Cảnh chìm vào giấc ngủ sâu, chỉ dùng phân thân Nguyên Anh Sơ Kỳ để dấn thân vào con đường ngộ đạo. Con đường tiến cấp Hóa Thần không nằm ở công pháp hay đan dược, mà là cảm ngộ Thiên Đạo: Muốn Hóa Thần, trước hết phải Hóa Phàm!",
      visual_prompt: "Wang Lin meditating, extreme realm soul sleeping, avatar awakening...",
      animation: "Slow Pan Right",
      duration: 17.4
    },
    {
      scene_id: 5,
      voiceover: "Đặt chân đến lãnh thổ quốc gia tu chân cấp bốn, Vương Lâm thu liễm toàn bộ uy áp, hóa thân thành một phàm nhân áo vải bình dị. Hắn ngắt một cành lá liễu ngậm nơi khóe miệng, tự tay đan chiếc giỏ tre khoác lên lưng, chầm chậm bước đi trên con đường quan đạo giữa dòng người tấp nập.",
      visual_prompt: "Wang Lin as a humble mortal scholar in coarse cloth robes...",
      animation: "Pan Left",
      duration: 14.5
    },
    {
      scene_id: 6,
      voiceover: "Gia nhập vào đoàn xe của người phàm, tâm cảnh của Vương Lâm dần trở nên tĩnh lặng chưa từng có. Bốn trăm năm chém giết tích tụ thành huyết hải sát khí dày đặc như sương mù đỏ quấn quanh thân thể, nay dưới sự an yên của cõi trần bắt đầu tự động ngưng tụ, dung nhập vào từng mạch linh lực bên trong phân thân.",
      visual_prompt: "Wang Lin riding a fine steed calmly among mortal travelers...",
      animation: "Zoom In",
      duration: 15.6
    },
    {
      scene_id: 7,
      voiceover: "Theo đoàn xe tiến vào kinh thành sầm uất được trấn giữ bởi chín cây tháp trụ linh khí khổng lồ, Vương Lâm không chọn phồn hoa danh lợi, mà lặng lẽ thuê một gian tiệm nhỏ nằm sâu trong con ngõ vắng để mở cửa hàng khắc gỗ, bắt đầu chuỗi ngày ẩn cư giữa nhân gian.",
      visual_prompt: "Ancient Asian capital city with nine massive black pillars...",
      animation: "Tilt Down",
      duration: 12.5
    },
    {
      scene_id: 8,
      voiceover: "Mỗi một nhát dao gọt giũa trên từng khúc gỗ là một lần Vương Lâm tìm lại hơi ấm tình thân từ lời dạy của cha năm nào. Hình bóng người cha hiền từ với đôi bàn tay chai sạn và người mẹ dịu dàng ngóng con dần hiện hữu sống động dưới lưỡi khắc, chứa đựng trọn vẹn chân tình và linh vận thiên nhiên.",
      visual_prompt: "Close-up of Wang Lin's hands carving lifelike wooden statues of parents...",
      animation: "Zoom In",
      duration: 16.5
    },
    {
      scene_id: 9,
      voiceover: "Tháng ngày trôi qua, Vương Lâm đắm chìm hoàn toàn vào thế giới điêu khắc, từ dân làng thuở ấu thơ cho đến những dị thú thượng cổ, hung long nơi Tu Ma Hải đều lần lượt tái sinh dưới bàn tay hắn. Tiệm khắc gỗ của chàng thanh niên Vương Lâm dần trở nên nức tiếng khắp một vùng phụ cận.",
      visual_prompt: "Wooden workshop shelves filled with incredible wooden carvings...",
      animation: "Pan Right",
      duration: 15.0
    },
    {
      scene_id: 10,
      voiceover: "Bên cạnh việc đàm đạo, uống rượu trái cây cùng cậu bé hàng xóm Đại Ngưu, tầng sương đỏ sát khí ngập trời của hắn đã được cô đọng thu nhỏ chỉ còn một tấc, biến thành một nội lực sát đạo vô hình nhưng đủ sức trấn áp bất kỳ đối thủ nào.",
      visual_prompt: "Wang Lin sharing sweet fruit wine with young boy Dai Niu...",
      animation: "Zoom Out",
      duration: 14.2
    },
    {
      scene_id: 11,
      voiceover: "Tuy nhiên, khi Vương Lâm thử khắc họa những đại năng Hóa Thần Kỳ như Cổ Đế hay Mạnh Đà Tử, khúc gỗ liền lập tức vỡ vụn thành tro bụi! Khoảng cách giữa phàm nhân và Hóa Thần vẫn còn là một bức màn ngăn cách của quy luật Thiên Đạo mà hắn cần phải vượt qua.",
      visual_prompt: "Wang Lin carving God Transformation powerhouse, wood bursting into ash...",
      animation: "Dynamic Shake",
      duration: 16.8
    },
    {
      scene_id: 12,
      voiceover: "Trong lúc ấy, một bức tượng dị thú tuyệt tác do Vương Lâm khắc đã lọt vào mắt xanh của vương phủ quyền quý, kéo theo những biến cố khôn lường sắp sửa ập đến chốn hồng trần thanh tịnh. Liệu Vương Lâm có thể lĩnh ngộ trọn vẹn Thiên Đạo qua kiếp sống Hóa Phàm để thuận lợi bước chân vào cảnh giới Hóa Thần Kỳ? Các bạn hãy bấm Like, Đăng ký kênh và cùng chờ đón tập tiếp theo nhé!",
      visual_prompt: "Wealthy noble holding glowing beast carving heading to royal palace...",
      animation: "Zoom In",
      duration: 19.5
    }
  ]);

  const handleUpdateScene = (index: number, field: keyof SceneItem, value: any) => {
    const updated = [...scenes];
    updated[index] = { ...updated[index], [field]: value };
    setScenes(updated);
  };

  const handleAddScene = () => {
    const newId = scenes.length + 1;
    setScenes([
      ...scenes,
      {
        scene_id: newId,
        voiceover: "Nhập lời thoại thuyết minh cho phân cảnh mới...",
        visual_prompt: "Cinematic anime render...",
        animation: "Zoom In",
        duration: 15.0
      }
    ]);
  };

  const handleDeleteScene = (index: number) => {
    if (scenes.length <= 1) return;
    const updated = scenes.filter((_, i) => i !== index);
    setScenes(updated);
  };

  const handlePlayAudio = (sceneId: number) => {
    if (playingScene === sceneId && audioElement) {
      audioElement.pause();
      setPlayingScene(null);
      return;
    }

    if (audioElement) {
      audioElement.pause();
    }

    const numStr = String(sceneId).padStart(2, "0");
    const audioUrl = `/outputs/novel_audio/scene_${numStr}.mp3`;
    const audio = new Audio(audioUrl);
    
    audio.onended = () => {
      setPlayingScene(null);
    };

    audio.onerror = () => {
      toast.error(`Không tìm thấy audio Scene ${sceneId}`, {
        description: "Bấm 'Tạo Kịch Bản & CapCut' để sinh file âm thanh mới nhất."
      });
      setPlayingScene(null);
    };

    audio.play();
    setAudioElement(audio);
    setPlayingScene(sceneId);
  };

  const handleGenerateAI = async () => {
    setLoading(true);
    toast.info("Đang kết nối AI & Đọc tiểu thuyết Tiên Nghịch...", {
      description: `Đang phân tích timeline từ Tập ${currentEp} sang Tập ${nextEp}`
    });

    try {
      const res = await axios.post("/api/novel/recap", {
        current_episode: currentEp,
        voice: voice,
        tts_speed: ttsSpeed,
        canvas_ratio: canvasRatio,
        scenes: scenes,
        media_paths: mediaPaths
      });

      if (res.data && res.data.success) {
        setDraftFolder(res.data.draft_folder);
        if (res.data.scenes && res.data.scenes.length > 0) {
          setScenes(res.data.scenes);
        }
        toast.success(`🎉 Đã sản xuất thành công Project CapCut Tập ${nextEp}!`, {
          description: `Đường dẫn: ${res.data.draft_folder}`
        });
      } else {
        toast.error("Lỗi xử lý pipeline", {
          description: res.data?.error || "Không thể tạo kịch bản"
        });
      }
    } catch (err: any) {
      toast.error("Lỗi kết nối Server", {
        description: err.response?.data?.error || err.message || String(err)
      });
    } finally {
      setLoading(false);
    }
  };

  const handleSaveAsPipelineProject = async () => {
    try {
      const projectName = `Novel_TienNghich_Tap_${nextEp}`;
      const res = await axios.post("/api/pipeline-projects", {
        folder_name: projectName,
        config: {
          novel_recap_mode: true,
          current_episode: currentEp,
          next_episode: nextEp,
          tts_engine: ttsEngine,
          voice: voice,
          tts_speed: ttsSpeed,
          canvas_ratio: canvasRatio,
          video_speed: videoSpeed,
          volume_db: bgmVolume,
          font_size: fontSize,
          font_color: fontColor,
          scenes: scenes
        }
      });
      if (res.data.ok) {
        toast.success(`Đã lưu thành Pipeline Project: ${projectName}`, {
          description: "Bạn có thể vào tab 'Dự Án Video' để xem và đẩy vào Queue render!"
        });
      }
    } catch (err: any) {
      toast.error("Lỗi lưu dự án pipeline", { description: err.message });
    }
  };

  const totalDuration = scenes.reduce((acc, s) => acc + (s.duration || 15), 0);
  const minutes = Math.floor(totalDuration / 60);
  const seconds = Math.round(totalDuration % 60);

  return (
    <div className="flex-1 p-6 space-y-6 overflow-y-auto max-h-[calc(100vh-4rem)] bg-[#09090b]">
      {/* Top Banner */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 p-6 rounded-2xl bg-gradient-to-r from-amber-500/15 via-orange-500/5 to-transparent border border-amber-500/25">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Badge className="bg-amber-500/20 text-amber-300 border-amber-500/30 font-mono text-xs">
              <Sparkles className="w-3.5 h-3.5 mr-1 text-amber-400" /> Pipeline Studio Đa Năng
            </Badge>
            <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-xs">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse mr-1.5" />
              Tùy Biến Đầy Đủ (Không Fix Cứng)
            </Badge>
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
            Xưởng Biên Kịch & Dựng Video Tiểu Thuyết AI <span className="text-amber-400 font-serif">《仙逆》</span>
          </h1>
          <p className="text-sm text-zinc-400 mt-1">
            Đọc nguyên tác ➔ Đối chiếu timeline ➔ Tùy chỉnh Video/TTS/Sub ➔ Viết kịch bản Thuyết minh ➔ Tự tạo CapCut Draft.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            onClick={handleSaveAsPipelineProject}
            variant="outline"
            className="border-zinc-700 bg-zinc-900/80 hover:bg-zinc-800 text-zinc-200 text-xs font-semibold rounded-xl"
          >
            <PlaySquare className="w-4 h-4 mr-1.5 text-blue-400" /> Lưu Vào Pipeline Projects
          </Button>

          <Button
            onClick={handleGenerateAI}
            disabled={loading}
            className="bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-600 hover:to-amber-700 text-zinc-950 font-bold px-5 py-2.5 rounded-xl shadow-lg shadow-amber-500/20 transition-all active:scale-95 text-xs"
          >
            {loading ? (
              <>
                <RefreshCw className="w-4 h-4 mr-2 animate-spin text-zinc-950" />
                Đang Sản Xuất Video...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4 mr-2 text-zinc-950" />
                1-Click Tạo Kịch Bản & CapCut Draft
              </>
            )}
          </Button>
        </div>
      </div>

      {/* 3-Column Studio Grid: (1) Story & Media, (2) Voice & Sub, (3) Scenes Editor */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Column: Story, Episode & Media */}
        <div className="lg:col-span-4 space-y-5">
          
          {/* Card 1: Story Timeline */}
          <Card className="bg-[#121216]/90 border-zinc-800/80 rounded-2xl shadow-sm">
            <CardHeader className="pb-3 border-b border-zinc-800/50">
              <CardTitle className="text-sm text-zinc-200 flex items-center gap-2">
                <BookOpen className="w-4 h-4 text-amber-400" />
                1. Mốc Phim Anime & Chương Tiểu Thuyết
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 space-y-3.5">
              <div className="space-y-1">
                <label className="text-xs font-medium text-zinc-300">Bộ Tiểu Thuyết</label>
                <select
                  value={novelName}
                  onChange={(e) => setNovelName(e.target.value)}
                  className="w-full h-9 px-3 rounded-xl bg-zinc-900/80 border border-zinc-800 text-xs text-zinc-200 outline-none focus:border-amber-500"
                >
                  <option value="xianni">Tiên Nghịch (Nhĩ Căn) - 2,073 Chương</option>
                  <option value="custom">Tùy Chọn Tiểu Thuyết Khác...</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-zinc-300 flex items-center gap-1">
                    <Tv className="w-3.5 h-3.5 text-zinc-400" /> Tập Đã Xem Xong
                  </label>
                  <Input
                    type="number"
                    value={currentEp}
                    onChange={(e) => {
                      const v = parseInt(e.target.value) || 1;
                      setCurrentEp(v);
                      setNextEp(v + 1);
                    }}
                    className="bg-zinc-900/80 border-zinc-800 text-white rounded-xl text-xs h-9 focus-visible:ring-amber-500/50"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-medium text-zinc-400 flex items-center gap-1">
                    <Film className="w-3.5 h-3.5 text-amber-400" /> Tập Sẽ Thuyết Minh
                  </label>
                  <Input
                    type="number"
                    value={nextEp}
                    onChange={(e) => setNextEp(parseInt(e.target.value) || 1)}
                    className="bg-zinc-900/40 border-zinc-800/50 rounded-xl text-xs h-9 font-bold text-amber-400 font-mono"
                  />
                </div>
              </div>

              <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-[11px] text-amber-200/90 space-y-1 leading-relaxed">
                <div className="font-semibold text-amber-300 flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5 text-amber-400" /> Đối Chiếu Nguyên Tác:
                </div>
                <p>• <strong>Tập {currentEp}:</strong> Mốc Chương 246 (Diệt Đằng gia)</p>
                <p>• <strong>Tập {nextEp}:</strong> Chương 247 ➔ 254 (Vương Lâm Hóa Phàm)</p>
              </div>
            </CardContent>
          </Card>

          {/* Card 2: Media, Video & Canvas Settings */}
          <Card className="bg-[#121216]/90 border-zinc-800/80 rounded-2xl shadow-sm">
            <CardHeader className="pb-3 border-b border-zinc-800/50">
              <CardTitle className="text-sm text-zinc-200 flex items-center gap-2">
                <Video className="w-4 h-4 text-blue-400" />
                2. Cấu Hình Video & Khung Hình (Canvas)
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 space-y-3.5 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-zinc-300 font-medium">Tỷ Lệ Khung Hình</label>
                  <select
                    value={canvasRatio}
                    onChange={(e) => setCanvasRatio(e.target.value)}
                    className="w-full h-9 px-3 rounded-xl bg-zinc-900/80 border border-zinc-800 text-zinc-200 outline-none"
                  >
                    <option value="16:9">16:9 (YouTube Ngang)</option>
                    <option value="9:16">9:16 (TikTok/Shorts Dọc)</option>
                    <option value="1:1">1:1 (Vuông)</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="text-zinc-300 font-medium">Tốc Độ Video</label>
                  <Input
                    type="number"
                    step="0.05"
                    value={videoSpeed}
                    onChange={(e) => setVideoSpeed(parseFloat(e.target.value) || 1.0)}
                    className="bg-zinc-900/80 border-zinc-800 text-white rounded-xl text-xs h-9"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-zinc-300 font-medium">Âm Lượng Nhạc Nền BGM (dB)</label>
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    step="0.5"
                    value={bgmVolume}
                    onChange={(e) => setBgmVolume(parseFloat(e.target.value) || -16)}
                    className="bg-zinc-900/80 border-zinc-800 text-white rounded-xl text-xs h-9"
                  />
                  <span className="text-zinc-500 font-mono text-xs">dB</span>
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-zinc-300 font-medium">Thêm Video/Ảnh Minh Họa Nguồn</label>
                <div className="p-3 rounded-xl border border-dashed border-zinc-700 bg-zinc-900/40 text-center space-y-1">
                  <Upload className="w-5 h-5 text-zinc-400 mx-auto" />
                  <p className="text-[11px] text-zinc-400">Kéo thả video/ảnh vào đây hoặc AI tự tạo ảnh</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Card 3: Voice TTS & Subtitle Typography */}
          <Card className="bg-[#121216]/90 border-zinc-800/80 rounded-2xl shadow-sm">
            <CardHeader className="pb-3 border-b border-zinc-800/50">
              <CardTitle className="text-sm text-zinc-200 flex items-center gap-2">
                <Volume2 className="w-4 h-4 text-emerald-400" />
                3. Lồng Tiếng AI (TTS) & Phụ Đề
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 space-y-3.5 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-zinc-300 font-medium">Voice Engine</label>
                  <select
                    value={ttsEngine}
                    onChange={(e) => setTtsEngine(e.target.value)}
                    className="w-full h-9 px-3 rounded-xl bg-zinc-900/80 border border-zinc-800 text-zinc-200 outline-none"
                  >
                    <option value="edge-tts">Edge-TTS (Miễn phí / Nhanh)</option>
                    <option value="minimax">Minimax (Cao cấp)</option>
                    <option value="openai">OpenAI TTS</option>
                    <option value="elevenlabs">ElevenLabs</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="text-zinc-300 font-medium">Tốc Độ Đọc (Rate)</label>
                  <Input
                    type="number"
                    step="0.05"
                    value={ttsSpeed}
                    onChange={(e) => setTtsSpeed(parseFloat(e.target.value) || 1.1)}
                    className="bg-zinc-900/80 border-zinc-800 text-white rounded-xl text-xs h-9"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-zinc-300 font-medium">Chọn Giọng Đọc</label>
                <select
                  value={voice}
                  onChange={(e) => setVoice(e.target.value)}
                  className="w-full h-9 px-3 rounded-xl bg-zinc-900/80 border border-zinc-800 text-zinc-200 outline-none"
                >
                  <option value="vi-VN-NamMinhNeural">Nam Minh (Giọng Nam Trầm Ấm Kịch Tính - Mặc định)</option>
                  <option value="vi-VN-HoaiMyNeural">Hoài My (Giọng Nữ Nhẹ Nhàng)</option>
                  <option value="zh-CN-YunxiNeural">Vân Hi (Tiếng Trung Phim Tu Tiên)</option>
                  <option value="en-US-ChristopherNeural">Christopher (Tiếng Anh Storyteller)</option>
                </select>
              </div>

              <div className="grid grid-cols-3 gap-2">
                <div className="space-y-1">
                  <label className="text-zinc-400">Cỡ Chữ (Font)</label>
                  <Input
                    type="number"
                    value={fontSize}
                    onChange={(e) => setFontSize(parseFloat(e.target.value) || 11.0)}
                    className="bg-zinc-900/80 border-zinc-800 text-white rounded-xl text-xs h-8"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-zinc-400">Màu Chữ</label>
                  <div className="flex items-center gap-1.5 h-8">
                    <input
                      type="color"
                      value={fontColor}
                      onChange={(e) => setFontColor(e.target.value)}
                      className="w-7 h-7 rounded-lg cursor-pointer bg-transparent border-0"
                    />
                    <span className="text-[10px] font-mono text-zinc-400">{fontColor}</span>
                  </div>
                </div>
                <div className="space-y-1">
                  <label className="text-zinc-400">Màu Viền</label>
                  <div className="flex items-center gap-1.5 h-8">
                    <input
                      type="color"
                      value={borderColor}
                      onChange={(e) => setBorderColor(e.target.value)}
                      className="w-7 h-7 rounded-lg cursor-pointer bg-transparent border-0"
                    />
                    <span className="text-[10px] font-mono text-zinc-400">{borderColor}</span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* CapCut Draft Result Status */}
          {draftFolder && (
            <Card className="bg-[#121216]/90 border-emerald-500/30 rounded-2xl shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-emerald-400 flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4" /> CapCut Draft Đã Sẵn Sàng
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4 pt-0 space-y-2 text-xs">
                <div className="p-2.5 rounded-xl bg-zinc-900/80 border border-zinc-800 text-zinc-300 font-mono text-[11px] break-all">
                  {draftFolder}
                </div>
                <p className="text-zinc-400">
                  Project đã được tạo trên máy. Bạn có thể mở CapCut PC lên để xem ngay!
                </p>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right Column: 12 Interactive Editable Scenes */}
        <div className="lg:col-span-8 space-y-4">
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-amber-400" />
              <h2 className="text-sm font-semibold text-white">Danh Sách Phân Cảnh ({scenes.length} Scenes)</h2>
            </div>
            
            <div className="flex items-center gap-3">
              <span className="text-xs font-mono text-amber-400 bg-amber-500/10 px-2.5 py-1 rounded-lg border border-amber-500/20 flex items-center gap-1">
                <Clock className="w-3 h-3" /> Tổng thời lượng: ~ {minutes}m {seconds}s
              </span>

              <Button
                size="sm"
                variant="outline"
                onClick={handleAddScene}
                className="h-8 text-xs border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-200"
              >
                <Plus className="w-3.5 h-3.5 mr-1" /> Thêm Cảnh
              </Button>
            </div>
          </div>

          {/* Editable Scenes Scroll Area */}
          <div className="space-y-3.5">
            {scenes.map((scene, idx) => {
              const isPlaying = playingScene === scene.scene_id;
              return (
                <div
                  key={scene.scene_id || idx}
                  className="p-4 rounded-xl bg-[#121216]/90 border border-zinc-800/80 hover:border-amber-500/30 transition-all space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded-md text-[11px] font-bold bg-amber-500/15 text-amber-300 border border-amber-500/20 font-mono">
                        SCENE {String(idx + 1).padStart(2, "0")}
                      </span>

                      <select
                        value={scene.animation || "Zoom In"}
                        onChange={(e) => handleUpdateScene(idx, "animation", e.target.value)}
                        className="h-6 px-2 rounded-md bg-zinc-900 border border-zinc-800 text-[11px] text-zinc-300 outline-none"
                      >
                        <option value="Zoom In">Hiệu ứng: Zoom In</option>
                        <option value="Zoom Out">Hiệu ứng: Zoom Out</option>
                        <option value="Pan Left">Hiệu ứng: Pan Left</option>
                        <option value="Pan Right">Hiệu ứng: Pan Right</option>
                        <option value="Tilt Down">Hiệu ứng: Tilt Down</option>
                        <option value="Dynamic Shake">Hiệu ứng: Dynamic Shake</option>
                      </select>
                    </div>

                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-1 text-[11px] text-zinc-400 font-mono">
                        <span>⏱️</span>
                        <Input
                          type="number"
                          step="0.1"
                          value={scene.duration || 15}
                          onChange={(e) => handleUpdateScene(idx, "duration", parseFloat(e.target.value) || 15)}
                          className="w-14 h-6 text-[11px] px-1 bg-zinc-900 border-zinc-800 text-white rounded text-center"
                        />
                        <span>s</span>
                      </div>

                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handlePlayAudio(scene.scene_id)}
                        className={`h-6 px-2 rounded-md text-[11px] font-medium border ${
                          isPlaying
                            ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                            : "bg-zinc-900 text-zinc-300 border-zinc-800 hover:bg-zinc-800"
                        }`}
                      >
                        {isPlaying ? (
                          <>
                            <Pause className="w-3 h-3 mr-1 text-amber-400" /> Tạm Dừng
                          </>
                        ) : (
                          <>
                            <Play className="w-3 h-3 mr-1 text-amber-400" /> Nghe Audio
                          </>
                        )}
                      </Button>

                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleDeleteScene(idx)}
                        className="h-6 w-6 p-0 text-zinc-500 hover:text-red-400 hover:bg-zinc-900 rounded"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>

                  {/* Editable Voiceover Textarea */}
                  <textarea
                    value={scene.voiceover}
                    onChange={(e) => handleUpdateScene(idx, "voiceover", e.target.value)}
                    rows={3}
                    className="w-full p-2.5 rounded-lg bg-zinc-900/80 border border-zinc-800 text-xs text-zinc-200 leading-relaxed outline-none focus:border-amber-500/50 resize-y"
                    placeholder="Nhập lời thoại cho phân cảnh..."
                  />

                  {/* Editable Visual Prompt */}
                  <div className="flex items-center gap-2 text-[11px] text-zinc-400">
                    <span className="shrink-0">🎨 Visual Prompt:</span>
                    <Input
                      type="text"
                      value={scene.visual_prompt || ""}
                      onChange={(e) => handleUpdateScene(idx, "visual_prompt", e.target.value)}
                      className="h-6 text-[11px] px-2 bg-zinc-900/60 border-zinc-800/80 text-zinc-300 rounded flex-1"
                      placeholder="Prompt tiếng Anh để sinh ảnh anime tương ứng..."
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
