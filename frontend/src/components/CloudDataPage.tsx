import React, { useState, useEffect } from "react";
import {
  Cloud,
  HardDrive,
  Download,
  Package,
  RefreshCw,
  Search,
  Film,
  Image,
  FileText,
  Volume2,
  FileCode,
  Sparkles,
  Layers,
  ChevronDown,
  ChevronUp,
  FolderDown,
  Database
} from "lucide-react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";
import { Card, CardContent } from "./ui/card";
import { toast } from "sonner";
import {
  fetchCloudAssets,
  fetchCloudEpisodes,
  fetchCloudManifest,
  rescanCloudAssets,
  getCloudDownloadUrl,
  getEpisodeBundleDownloadUrl,
  type CloudAsset,
  type CloudEpisodeBundle,
  type CloudManifest
} from "../lib/api";

export const CloudDataPage: React.FC = () => {
  const [episodes, setEpisodes] = useState<CloudEpisodeBundle[]>([]);
  const [assets, setAssets] = useState<CloudAsset[]>([]);
  const [manifest, setManifest] = useState<CloudManifest | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRescanning, setIsRescanning] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<"episodes" | "all_files">("episodes");

  // Filters
  const [selectedNovel, setSelectedNovel] = useState<string>("all");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [expandedEpisode, setExpandedEpisode] = useState<string | null>("Phamnhantutien_ep186");

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [epRes, assetRes, manRes] = await Promise.all([
        fetchCloudEpisodes(),
        fetchCloudAssets({ limit: 300 }),
        fetchCloudManifest().catch(() => ({ success: false, manifest: null as any }))
      ]);

      if (epRes.success) setEpisodes(epRes.episodes || []);
      if (assetRes.success) setAssets(assetRes.assets || []);
      if (manRes.success) setManifest(manRes.manifest);
    } catch (err: any) {
      toast.error("Lỗi tải danh mục dữ liệu Cloud", {
        description: err.message || String(err)
      });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleRescan = async () => {
    setIsRescanning(true);
    try {
      const res = await rescanCloudAssets();
      if (res.success) {
        toast.success("Đã đồng bộ và lập chỉ mục Google Drive 5TB!", {
          description: `Tổng số: ${res.manifest?.total_assets || 0} tài nguyên.`
        });
        await loadData();
      }
    } catch (err: any) {
      toast.error("Lỗi quét lại Google Drive", { description: err.message });
    } finally {
      setIsRescanning(false);
    }
  };

  const getCategoryBadge = (cat: string) => {
    switch (cat) {
      case "video_raw":
        return <Badge className="bg-purple-900/60 text-purple-300 border-purple-700/50"><Film className="w-3 h-3 mr-1" /> Video Gốc</Badge>;
      case "keyframes":
        return <Badge className="bg-amber-900/60 text-amber-300 border-amber-700/50"><Image className="w-3 h-3 mr-1" /> Keyframes</Badge>;
      case "scene_analysis":
        return <Badge className="bg-emerald-900/60 text-emerald-300 border-emerald-700/50"><Sparkles className="w-3 h-3 mr-1" /> Phân Cảnh JSON</Badge>;
      case "srt_subtitles":
        return <Badge className="bg-blue-900/60 text-blue-300 border-blue-700/50"><FileText className="w-3 h-3 mr-1" /> Phụ Đề SRT</Badge>;
      case "script":
        return <Badge className="bg-cyan-900/60 text-cyan-300 border-cyan-700/50"><FileCode className="w-3 h-3 mr-1" /> Kịch Bản</Badge>;
      case "audio_tts":
        return <Badge className="bg-pink-900/60 text-pink-300 border-pink-700/50"><Volume2 className="w-3 h-3 mr-1" /> Audio TTS</Badge>;
      case "visuals_dataset":
        return <Badge className="bg-indigo-900/60 text-indigo-300 border-indigo-700/50"><Layers className="w-3 h-3 mr-1" /> Dataset Nhân Vật</Badge>;
      default:
        return <Badge variant="outline">{cat}</Badge>;
    }
  };

  // Filtered lists
  const filteredEpisodes = episodes.filter((ep) => {
    if (selectedNovel !== "all" && ep.novel_id !== selectedNovel) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        ep.novel_title.toLowerCase().includes(q) ||
        ep.novel_id.toLowerCase().includes(q) ||
        String(ep.episode).includes(q)
      );
    }
    return true;
  });

  const filteredAssets = assets.filter((a) => {
    if (selectedNovel !== "all" && a.novel_id !== selectedNovel) return false;
    if (selectedCategory !== "all" && a.category !== selectedCategory) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        a.filename.toLowerCase().includes(q) ||
        a.novel_title.toLowerCase().includes(q) ||
        a.category.toLowerCase().includes(q) ||
        String(a.episode).includes(q)
      );
    }
    return true;
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Header Bar */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 bg-[#121216] border border-zinc-800/80 p-6 rounded-2xl shadow-xl">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shadow-inner">
              <Cloud className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-xl md:text-2xl font-bold tracking-tight text-zinc-100 flex items-center gap-2">
                Kho Dữ Liệu Cloud & Tải Xuống
                <Badge className="bg-emerald-950 text-emerald-400 border border-emerald-700/60 font-mono text-xs">
                  5TB Google Drive Active
                </Badge>
              </h1>
              <p className="text-xs md:text-sm text-zinc-400">
                Toàn bộ Video gốc, Keyframes, Subtitle SRT, Kịch bản & Audio được định nghĩa chuẩn, sẵn sàng tải xuống mọi lúc.
              </p>
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-3 w-full md:w-auto">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRescan}
            disabled={isRescanning}
            className="border-zinc-700 hover:bg-zinc-800 text-zinc-300 gap-2 font-medium"
          >
            <RefreshCw className={`w-4 h-4 ${isRescanning ? "animate-spin text-emerald-400" : ""}`} />
            {isRescanning ? "Đang quét Drive..." : "Quét Lại Drive 5TB"}
          </Button>
        </div>
      </div>

      {/* Storage Statistics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="bg-[#121216]/90 border-zinc-800/80">
          <CardContent className="p-5 flex items-center justify-between">
            <div>
              <p className="text-xs text-zinc-400 font-medium uppercase tracking-wider">Đã Định Nghĩa</p>
              <p className="text-2xl font-bold text-zinc-100 mt-1">
                {manifest?.total_assets || assets.length} <span className="text-sm font-normal text-zinc-400">tài nguyên</span>
              </p>
            </div>
            <div className="p-3 bg-blue-500/10 rounded-xl border border-blue-500/20 text-blue-400">
              <HardDrive className="w-5 h-5" />
            </div>
          </CardContent>
        </Card>

        <Card className="bg-[#121216]/90 border-zinc-800/80">
          <CardContent className="p-5 flex items-center justify-between">
            <div>
              <p className="text-xs text-zinc-400 font-medium uppercase tracking-wider">Dung Lượng Trên Drive</p>
              <p className="text-2xl font-bold text-emerald-400 mt-1">
                {manifest?.total_size_mb || 0} <span className="text-sm font-normal text-zinc-400">MB</span>
              </p>
            </div>
            <div className="p-3 bg-emerald-500/10 rounded-xl border border-emerald-500/20 text-emerald-400">
              <Cloud className="w-5 h-5" />
            </div>
          </CardContent>
        </Card>

        <Card className="bg-[#121216]/90 border-zinc-800/80">
          <CardContent className="p-5 flex items-center justify-between">
            <div>
              <p className="text-xs text-zinc-400 font-medium uppercase tracking-wider">Tập Phim Đã Phân Tích</p>
              <p className="text-2xl font-bold text-amber-400 mt-1">
                {episodes.length} <span className="text-sm font-normal text-zinc-400">tập</span>
              </p>
            </div>
            <div className="p-3 bg-amber-500/10 rounded-xl border border-amber-500/20 text-amber-400">
              <Film className="w-5 h-5" />
            </div>
          </CardContent>
        </Card>

        <Card className="bg-[#121216]/90 border-zinc-800/80">
          <CardContent className="p-5 flex items-center justify-between">
            <div>
              <p className="text-xs text-zinc-400 font-medium uppercase tracking-wider">MongoDB Atlas</p>
              <div className="flex items-center gap-1.5 mt-1">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <p className="text-sm font-semibold text-emerald-400">Đã Đồng Bộ Schema</p>
              </div>
            </div>
            <div className="p-3 bg-purple-500/10 rounded-xl border border-purple-500/20 text-purple-400">
              <Database className="w-5 h-5" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* View Switcher & Filters */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 bg-[#121216] border border-zinc-800/80 p-4 rounded-xl">
        {/* Tab switcher */}
        <div className="flex items-center bg-zinc-900/90 p-1 rounded-lg border border-zinc-800">
          <button
            onClick={() => setActiveTab("episodes")}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              activeTab === "episodes"
                ? "bg-zinc-800 text-emerald-400 shadow-sm"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Theo Tập Phim (Bundles)
          </button>
          <button
            onClick={() => setActiveTab("all_files")}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              activeTab === "all_files"
                ? "bg-zinc-800 text-emerald-400 shadow-sm"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Toàn Bộ File ({assets.length})
          </button>
        </div>

        {/* Filter controls */}
        <div className="flex flex-wrap items-center gap-3 w-full md:w-auto">
          {/* Search */}
          <div className="relative flex-1 md:w-60">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-zinc-500" />
            <Input
              type="text"
              placeholder="Tìm kiếm file, tập..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 bg-zinc-900 border-zinc-700/70 text-zinc-200 text-xs h-9"
            />
          </div>

          {/* Novel filter */}
          <select
            value={selectedNovel}
            onChange={(e) => setSelectedNovel(e.target.value)}
            className="bg-zinc-900 border border-zinc-700/70 text-zinc-200 text-xs rounded-md px-3 h-9 focus:outline-none focus:border-emerald-500"
          >
            <option value="all">Tất cả truyện</option>
            <option value="Phamnhantutien">Phàm Nhân Tu Tiên</option>
            <option value="xianni">Tiên Nghịch</option>
          </select>

          {/* Category filter (chỉ khi xem all files) */}
          {activeTab === "all_files" && (
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="bg-zinc-900 border border-zinc-700/70 text-zinc-200 text-xs rounded-md px-3 h-9 focus:outline-none focus:border-emerald-500"
            >
              <option value="all">Tất cả loại file</option>
              <option value="keyframes">Keyframes</option>
              <option value="scene_analysis">Phân cảnh JSON</option>
              <option value="srt_subtitles">Phụ đề SRT</option>
              <option value="video_raw">Video Gốc</option>
              <option value="audio_tts">Audio Giọng Đọc</option>
              <option value="visuals_dataset">Dataset</option>
            </select>
          )}
        </div>
      </div>

      {/* Main Content View */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center p-16 space-y-4 text-zinc-400 bg-[#121216] border border-zinc-800 rounded-2xl">
          <RefreshCw className="w-8 h-8 animate-spin text-emerald-400" />
          <p className="text-sm">Đang nạp danh mục tài nguyên từ Google Drive 5TB...</p>
        </div>
      ) : activeTab === "episodes" ? (
        /* Episode Bundles View */
        <div className="space-y-4">
          {filteredEpisodes.length === 0 ? (
            <div className="p-12 text-center text-zinc-400 bg-[#121216] border border-zinc-800 rounded-2xl">
              <Package className="w-10 h-10 mx-auto mb-3 text-zinc-600" />
              <p className="text-base font-medium text-zinc-300">Không tìm thấy tập phim nào</p>
              <p className="text-xs text-zinc-500 mt-1">Hãy bấm "Quét Lại Drive 5TB" để cập nhật dữ liệu.</p>
            </div>
          ) : (
            filteredEpisodes.map((ep) => {
              const isExpanded = expandedEpisode === ep.bundle_key;
              const bundleDownloadUrl = getEpisodeBundleDownloadUrl(ep.novel_id, ep.episode);

              return (
                <div
                  key={ep.bundle_key}
                  className="bg-[#121216] border border-zinc-800/80 rounded-2xl overflow-hidden shadow-lg transition-all"
                >
                  {/* Episode Card Header */}
                  <div className="p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 bg-gradient-to-r from-zinc-900/80 to-[#121216]">
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 font-bold text-lg">
                        {ep.episode}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="text-lg font-bold text-zinc-100">{ep.novel_title}</h3>
                          <Badge className="bg-amber-950 text-amber-300 border border-amber-700/60 text-xs">
                            Tập {ep.episode}
                          </Badge>
                        </div>
                        <p className="text-xs text-zinc-400 mt-0.5">
                          {ep.total_files} files • {ep.total_size_mb} MB trên Google Drive
                        </p>
                      </div>
                    </div>

                    {/* Available Assets Badges */}
                    <div className="flex flex-wrap items-center gap-2">
                      {ep.has_scenes_analysis && (
                        <Badge className="bg-emerald-950 text-emerald-300 border-emerald-700/50 text-xs">
                          <Sparkles className="w-3 h-3 mr-1" /> {ep.scenes_count} Cảnh Phân Tích
                        </Badge>
                      )}
                      {ep.keyframes_count > 0 && (
                        <Badge className="bg-amber-950 text-amber-300 border-amber-700/50 text-xs">
                          <Image className="w-3 h-3 mr-1" /> {ep.keyframes_count} Keyframes
                        </Badge>
                      )}
                      {ep.has_subtitles && (
                        <Badge className="bg-blue-950 text-blue-300 border-blue-700/50 text-xs">
                          <FileText className="w-3 h-3 mr-1" /> Phụ Đề SRT
                        </Badge>
                      )}
                      {ep.has_raw_video && (
                        <Badge className="bg-purple-950 text-purple-300 border-purple-700/50 text-xs">
                          <Film className="w-3 h-3 mr-1" /> Video Gốc
                        </Badge>
                      )}
                    </div>

                    {/* Download & Expand Buttons */}
                    <div className="flex items-center gap-2 w-full md:w-auto">
                      <a
                        href={bundleDownloadUrl}
                        download
                        className="flex-1 md:flex-initial inline-flex items-center justify-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-semibold shadow-md transition-all"
                      >
                        <FolderDown className="w-4 h-4" />
                        Tải Trọn Bộ ZIP (Tập {ep.episode})
                      </a>

                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setExpandedEpisode(isExpanded ? null : ep.bundle_key)}
                        className="text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800"
                      >
                        {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </Button>
                    </div>
                  </div>

                  {/* Expanded Asset List & Keyframe Preview */}
                  {isExpanded && (
                    <div className="p-5 border-t border-zinc-800/80 bg-zinc-950/40 space-y-4">
                      {/* Keyframes Gallery Preview */}
                      {ep.assets.some((a) => a.category === "keyframes") && (
                        <div>
                          <p className="text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wider">
                            Hình Ảnh Khung Hình (Keyframes) Trích Xuất
                          </p>
                          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-3">
                            {ep.assets
                              .filter((a) => a.category === "keyframes")
                              .slice(0, 12)
                              .map((kf) => (
                                <div
                                  key={kf.asset_id}
                                  className="group relative rounded-lg overflow-hidden border border-zinc-800 bg-zinc-900 aspect-video flex flex-col justify-end"
                                >
                                  <img
                                    src={`/api/novel/scenes/thumbnail?novel_id=${ep.novel_id}&episode=${ep.episode}&filename=${kf.filename}`}
                                    alt={kf.filename}
                                    className="absolute inset-0 w-full h-full object-cover transition-transform group-hover:scale-105"
                                    loading="lazy"
                                    onError={(e) => {
                                      // Fallback direct download link if thumbnail route misses
                                      (e.target as HTMLImageElement).src = getCloudDownloadUrl(kf.relative_path);
                                    }}
                                  />
                                  <div className="relative z-10 bg-gradient-to-t from-black/90 to-transparent p-1.5 flex items-center justify-between text-[10px]">
                                    <span className="truncate text-zinc-300 font-mono">{kf.filename.replace("keyframe_", "kf_")}</span>
                                    <a
                                      href={getCloudDownloadUrl(kf.asset_id)}
                                      download
                                      className="text-emerald-400 hover:text-emerald-300 p-1"
                                      title="Tải ảnh về máy"
                                    >
                                      <Download className="w-3 h-3" />
                                    </a>
                                  </div>
                                </div>
                              ))}
                          </div>
                        </div>
                      )}

                      {/* File Details Table */}
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs">
                          <thead className="bg-zinc-900/80 text-zinc-400 uppercase text-[10px] tracking-wider border-b border-zinc-800">
                            <tr>
                              <th className="py-2.5 px-3">Tên File / Tài Nguyên</th>
                              <th className="py-2.5 px-3">Phân Loại</th>
                              <th className="py-2.5 px-3">Dung Lượng</th>
                              <th className="py-2.5 px-3">Đường Dẫn Trên Drive</th>
                              <th className="py-2.5 px-3 text-right">Tải Xuống</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-zinc-800/60 font-mono text-[11px]">
                            {ep.assets.map((asset) => (
                              <tr key={asset.asset_id} className="hover:bg-zinc-900/40 text-zinc-300">
                                <td className="py-2.5 px-3 font-semibold text-zinc-200">
                                  {asset.filename}
                                </td>
                                <td className="py-2.5 px-3">{getCategoryBadge(asset.category)}</td>
                                <td className="py-2.5 px-3 text-zinc-400">{asset.size_mb} MB</td>
                                <td className="py-2.5 px-3 text-zinc-500 truncate max-w-xs" title={asset.drive_path}>
                                  {asset.relative_path}
                                </td>
                                <td className="py-2.5 px-3 text-right">
                                  <a
                                    href={getCloudDownloadUrl(asset.asset_id)}
                                    download
                                    className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-zinc-800 hover:bg-emerald-600 hover:text-white text-zinc-300 rounded-md transition-all font-sans text-[11px]"
                                  >
                                    <Download className="w-3 h-3" /> Tải về
                                  </a>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      ) : (
        /* All Files Flat Table View */
        <div className="bg-[#121216] border border-zinc-800 rounded-2xl overflow-hidden shadow-lg">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-zinc-900/80 text-zinc-400 uppercase text-[10px] tracking-wider border-b border-zinc-800">
                <tr>
                  <th className="py-3 px-4">Tên File</th>
                  <th className="py-3 px-4">Truyện & Tập</th>
                  <th className="py-3 px-4">Phân Loại</th>
                  <th className="py-3 px-4">Kích Thước</th>
                  <th className="py-3 px-4">Đường Dẫn Drive</th>
                  <th className="py-3 px-4 text-right">Hành Động</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60 font-mono text-[11px]">
                {filteredAssets.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-zinc-500">
                      Không tìm thấy file nào phù hợp với bộ lọc
                    </td>
                  </tr>
                ) : (
                  filteredAssets.map((asset) => (
                    <tr key={asset.asset_id} className="hover:bg-zinc-900/40 text-zinc-300">
                      <td className="py-3 px-4 font-semibold text-zinc-200">
                        {asset.filename}
                      </td>
                      <td className="py-3 px-4 font-sans text-zinc-400">
                        {asset.novel_title} (Tập {asset.episode})
                      </td>
                      <td className="py-3 px-4 font-sans">{getCategoryBadge(asset.category)}</td>
                      <td className="py-3 px-4 text-zinc-400">{asset.size_mb} MB</td>
                      <td className="py-3 px-4 text-zinc-500 truncate max-w-sm" title={asset.drive_path}>
                        {asset.relative_path}
                      </td>
                      <td className="py-3 px-4 text-right font-sans">
                        <a
                          href={getCloudDownloadUrl(asset.asset_id)}
                          download
                          className="inline-flex items-center gap-1.5 px-3 py-1 bg-zinc-800 hover:bg-emerald-600 hover:text-white text-zinc-300 rounded-md transition-all text-xs"
                        >
                          <Download className="w-3.5 h-3.5" /> Tải về
                        </a>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default CloudDataPage;
