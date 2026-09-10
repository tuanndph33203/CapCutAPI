import React, { useState, useEffect, useRef } from "react";
import { 
  Dialog, 
  DialogContent, 
  DialogTitle, 
  DialogDescription, 
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";
import { toast } from "sonner";
import { 
  BookOpen, 
  FolderPlus, 
  Globe, 
  RefreshCw, 
  Layers, 
  Trash2,
  Upload,
  FileCheck,
  Edit3,
  BookText,
  Save,
  Search,
  ArrowLeft,
  Check,
  Tag,
  Wand2
} from "lucide-react";
import axios from "axios";

interface NovelItem {
  id: string;
  name: string;
  chapters_count: number;
  path: string;
  source?: string;
}

interface ChapterItem {
  index: number;
  chapter_num?: number;
  filename: string;
  title: string;
  search_keys?: string[];
  size_kb: number;
  word_count?: number;
  modified_time?: number;
}

interface NovelImportModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedNovelId: string;
  onSelectNovel: (novel: NovelItem) => void;
}

export const NovelImportModal: React.FC<NovelImportModalProps> = ({
  open,
  onOpenChange,
  selectedNovelId,
  onSelectNovel,
}) => {
  const [novels, setNovels] = useState<NovelItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<"list" | "files" | "folder" | "url" | "editor">("list");

  // Form States for Import
  const [novelName, setNovelName] = useState<string>("");
  const [folderPath, setFolderPath] = useState<string>("");
  const [webUrl, setWebUrl] = useState<string>("");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [resplittingId, setResplittingId] = useState<string | null>(null);

  // Rename Novel State
  const [editingNovelId, setEditingNovelId] = useState<string | null>(null);
  const [editingNovelName, setEditingNovelName] = useState<string>("");

  // Chapter Editor States
  const [editingNovel, setEditingNovel] = useState<NovelItem | null>(null);
  const [chapters, setChapters] = useState<ChapterItem[]>([]);
  const [chapterSearch, setChapterSearch] = useState<string>("");
  const [selectedChapter, setSelectedChapter] = useState<ChapterItem | null>(null);
  const [chapterContent, setChapterContent] = useState<string>("");
  const [loadingChapter, setLoadingChapter] = useState<boolean>(false);
  const [savingChapter, setSavingChapter] = useState<boolean>(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchNovels = async () => {
    setLoading(true);
    try {
      const res = await axios.get("/api/novels");
      if (res.data?.success && Array.isArray(res.data.novels)) {
        setNovels(res.data.novels);
      }
    } catch (err: any) {
      console.error("Lỗi fetch novels:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      fetchNovels();
    }
  }, [open]);

  // 1. Handle Multiple Files Upload
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const fileList = Array.from(e.target.files);
      setSelectedFiles(fileList);
      if (!novelName) {
        const defaultName = fileList[0].name.replace(/\.[^/.]+$/, "").replace(/_chapters|_full|_all/i, "");
        setNovelName(defaultName);
      }
      toast.info(`Đã chọn ${fileList.length} file văn bản!`);
    }
  };

  const handleImportFiles = async () => {
    if (selectedFiles.length === 0) {
      toast.error("Vui lòng chọn ít nhất 1 file văn bản (.txt, .md)!");
      return;
    }
    if (!novelName) {
      toast.error("Vui lòng nhập tên bộ truyện!");
      return;
    }

    setIsSubmitting(true);
    toast.loading("Đang đọc, phân tách chương và tạo Search Keys...", { id: "upload_progress" });

    try {
      const filePayloads = await Promise.all(
        selectedFiles.map(async (file) => {
          return new Promise<{ filename: string; content: string }>((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (event) => {
              resolve({
                filename: file.name,
                content: (event.target?.result as string) || "",
              });
            };
            reader.onerror = (error) => reject(error);
            reader.readAsText(file, "UTF-8");
          });
        })
      );

      const res = await axios.post("/api/novels/upload-files", {
        novel_name: novelName,
        files: filePayloads,
      });

      if (res.data?.success) {
        toast.success(`🎉 Đã nhập thành công truyện '${novelName}' với ${res.data.chapters_count} chương!`, {
          id: "upload_progress",
        });
        setSelectedFiles([]);
        setNovelName("");
        if (fileInputRef.current) fileInputRef.current.value = "";
        await fetchNovels();
        setActiveTab("list");
      }
    } catch (err: any) {
      toast.error("Lỗi nhập file truyện", {
        description: err.response?.data?.error || err.message,
        id: "upload_progress",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  // 2. Handle Folder Import
  const handleImportFolder = async () => {
    if (!novelName || !folderPath) {
      toast.error("Vui lòng nhập đầy đủ tên truyện và đường dẫn thư mục!");
      return;
    }
    setIsSubmitting(true);
    try {
      const res = await axios.post("/api/novels/import-folder", {
        novel_name: novelName,
        folder_path: folderPath,
      });
      if (res.data?.success) {
        toast.success(`Đã nhập thành công truyện '${novelName}' với ${res.data.chapters_count} chương!`);
        setNovelName("");
        setFolderPath("");
        await fetchNovels();
        setActiveTab("list");
      }
    } catch (err: any) {
      toast.error("Lỗi nhập thư mục truyện", { description: err.response?.data?.error || err.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  // 3. Handle Web URL Import
  const handleImportUrl = async () => {
    if (!webUrl) {
      toast.error("Vui lòng nhập đường dẫn URL trang truyện!");
      return;
    }
    setIsSubmitting(true);
    try {
      const res = await axios.post("/api/novels/import-url", {
        novel_name: novelName || "Truyện Web",
        url: webUrl,
      });
      if (res.data?.success) {
        toast.success(`Đã cào dữ liệu và nhập ${res.data.chapters_count} chương thành công!`);
        setWebUrl("");
        setNovelName("");
        await fetchNovels();
        setActiveTab("list");
      }
    } catch (err: any) {
      toast.error("Lỗi cào truyện từ web", { description: err.response?.data?.error || err.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  // 4. Handle Rename Novel
  const handleSaveRename = async (novelId: string) => {
    if (!editingNovelName.trim()) {
      setEditingNovelId(null);
      return;
    }
    try {
      const res = await axios.post("/api/novels/rename", {
        novel_id: novelId,
        new_name: editingNovelName.trim(),
      });
      if (res.data?.success) {
        toast.success("Đã đổi tên truyện thành công!");
        setEditingNovelId(null);
        await fetchNovels();
      }
    } catch (err: any) {
      toast.error("Lỗi đổi tên truyện", { description: err.message });
    }
  };

  // 5. Handle Delete Novel
  const handleDeleteNovel = async (novel: NovelItem, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm(`Bạn có chắc chắn muốn xóa bộ truyện '${novel.name}' không?`)) {
      setDeletingId(novel.id);
      try {
        const res = await axios.post("/api/novels/delete", { novel_id: novel.id });
        if (res.data?.success) {
          toast.success(`Đã xóa bộ truyện '${novel.name}' thành công!`);
          await fetchNovels();
        }
      } catch (err: any) {
        toast.error("Lỗi xóa truyện", { description: err.response?.data?.error || err.message });
      } finally {
        setDeletingId(null);
      }
    }
  };

  // 6. Handle Re-split & Re-index Chapters
  const handleResplitNovel = async (novel: NovelItem, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setResplittingId(novel.id);
    toast.loading(`Đang phân tích, tách lại chương & tạo Search Keys cho '${novel.name}'...`, { id: "resplit_toast" });
    try {
      const res = await axios.post("/api/novels/resplit", { novel_id: novel.id });
      if (res.data?.success) {
        toast.success(`🎉 ${res.data.message}`, { id: "resplit_toast" });
        await fetchNovels();
        if (activeTab === "editor" && editingNovel?.id === novel.id) {
          await loadChaptersForNovel(novel);
        }
      }
    } catch (err: any) {
      toast.error("Lỗi tách chương", { description: err.response?.data?.error || err.message, id: "resplit_toast" });
    } finally {
      setResplittingId(null);
    }
  };

  // 7. Open Chapter Editor
  const loadChaptersForNovel = async (novel: NovelItem) => {
    setLoadingChapter(true);
    try {
      const res = await axios.get(`/api/novels/${encodeURIComponent(novel.id)}/chapters`);
      if (res.data?.success && Array.isArray(res.data.chapters)) {
        setChapters(res.data.chapters);
        if (res.data.chapters.length > 0) {
          handleSelectChapter(novel.id, res.data.chapters[0]);
        }
      }
    } catch (err: any) {
      toast.error("Lỗi tải danh sách chương", { description: err.message });
    } finally {
      setLoadingChapter(false);
    }
  };

  const handleOpenChapterEditor = async (novel: NovelItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingNovel(novel);
    setActiveTab("editor");
    await loadChaptersForNovel(novel);
  };

  const handleSelectChapter = async (novelId: string, chapter: ChapterItem) => {
    setSelectedChapter(chapter);
    setLoadingChapter(true);
    try {
      const res = await axios.get(`/api/novels/${encodeURIComponent(novelId)}/chapter?file=${encodeURIComponent(chapter.filename)}`);
      if (res.data?.success) {
        setChapterContent(res.data.content || "");
      }
    } catch (err: any) {
      toast.error("Lỗi đọc nội dung chương", { description: err.message });
    } finally {
      setLoadingChapter(false);
    }
  };

  const handleSaveChapter = async () => {
    if (!editingNovel || !selectedChapter) return;
    setSavingChapter(true);
    try {
      const res = await axios.post(`/api/novels/${encodeURIComponent(editingNovel.id)}/chapter`, {
        filename: selectedChapter.filename,
        content: chapterContent,
      });
      if (res.data?.success) {
        toast.success(`Đã lưu nội dung '${selectedChapter.title}' thành công!`);
      }
    } catch (err: any) {
      toast.error("Lỗi lưu chương", { description: err.message });
    } finally {
      setSavingChapter(false);
    }
  };

  const filteredChapters = chapters.filter((c) => {
    const q = chapterSearch.toLowerCase();
    const matchTitle = c.title.toLowerCase().includes(q);
    const matchIndex = String(c.index).includes(q) || String(c.chapter_num || "").includes(q);
    const matchKeys = c.search_keys?.some((k) => k.toLowerCase().includes(q));
    return matchTitle || matchIndex || matchKeys;
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl bg-[#0e0e12] border-zinc-800 text-zinc-100 p-0 overflow-hidden rounded-2xl shadow-2xl">
        {/* Header */}
        <div className="p-4 px-5 border-b border-zinc-800/80 bg-gradient-to-r from-amber-500/10 via-transparent to-transparent flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-amber-500/15 border border-amber-500/30 flex items-center justify-center text-amber-400">
              <BookOpen className="w-4 h-4" />
            </div>
            <div>
              <DialogTitle className="text-sm font-bold text-white flex items-center gap-2">
                {activeTab === "editor" ? `Chỉnh Sửa Văn Bản: ${editingNovel?.name}` : "Kho Tiểu Thuyết & Trình Biên Tập Chữ AI"}
              </DialogTitle>
              <DialogDescription className="text-xs text-zinc-400">
                {activeTab === "editor"
                  ? "Xem và chỉnh sửa trực tiếp nội dung từng chương truyện, Search Keys và lập chỉ mục."
                  : "Quản lý, phân tách chương thông minh, tự tạo Search Keys cho từng chương."}
              </DialogDescription>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {activeTab === "editor" ? (
              <div className="flex items-center gap-2">
                {editingNovel && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleResplitNovel(editingNovel)}
                    disabled={resplittingId === editingNovel.id}
                    className="h-7 text-xs border-amber-500/40 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300"
                    title="Tách lại toàn bộ chương từ file gốc và tạo lại Search Keys"
                  >
                    <Wand2 className={`w-3.5 h-3.5 mr-1 ${resplittingId === editingNovel.id ? "animate-spin" : ""}`} />
                    Tách Lại & Tạo Search Keys
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setActiveTab("list")}
                  className="h-7 text-xs border-zinc-700 bg-zinc-900 text-zinc-200"
                >
                  <ArrowLeft className="w-3.5 h-3.5 mr-1" /> Quay lại danh sách
                </Button>
              </div>
            ) : (
              <Button
                size="sm"
                variant="ghost"
                onClick={fetchNovels}
                className="h-7 px-2.5 text-xs text-zinc-400 hover:text-white"
              >
                <RefreshCw className={`w-3.5 h-3.5 mr-1 ${loading ? "animate-spin" : ""}`} /> Làm mới
              </Button>
            )}
          </div>
        </div>

        {/* Tab Buttons (Hide when in editor) */}
        {activeTab !== "editor" && (
          <div className="flex items-center gap-2 px-5 pt-2 border-b border-zinc-800/60 bg-zinc-950/40">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setActiveTab("list")}
              className={`h-8 text-xs font-semibold rounded-b-none border-b-2 ${
                activeTab === "list"
                  ? "border-amber-400 text-amber-300 bg-amber-500/10"
                  : "border-transparent text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <Layers className="w-3.5 h-3.5 mr-1.5" /> Danh Sách Truyện ({novels.length})
            </Button>

            <Button
              variant="ghost"
              size="sm"
              onClick={() => setActiveTab("files")}
              className={`h-8 text-xs font-semibold rounded-b-none border-b-2 ${
                activeTab === "files"
                  ? "border-amber-400 text-amber-300 bg-amber-500/10"
                  : "border-transparent text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <Upload className="w-3.5 h-3.5 mr-1.5" /> + Nhập 1 Hoặc Nhiều File
            </Button>

            <Button
              variant="ghost"
              size="sm"
              onClick={() => setActiveTab("folder")}
              className={`h-8 text-xs font-semibold rounded-b-none border-b-2 ${
                activeTab === "folder"
                  ? "border-amber-400 text-amber-300 bg-amber-500/10"
                  : "border-transparent text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <FolderPlus className="w-3.5 h-3.5 mr-1.5" /> + Nhập Từ Thư Mục
            </Button>

            <Button
              variant="ghost"
              size="sm"
              onClick={() => setActiveTab("url")}
              className={`h-8 text-xs font-semibold rounded-b-none border-b-2 ${
                activeTab === "url"
                  ? "border-amber-400 text-amber-300 bg-amber-500/10"
                  : "border-transparent text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <Globe className="w-3.5 h-3.5 mr-1.5" /> + Nhập Từ Link Web
            </Button>
          </div>
        )}

        {/* Tab Content */}
        <div className="p-5 max-h-[440px] overflow-y-auto space-y-4">
          
          {/* TAB 1: Danh sách truyện */}
          {activeTab === "list" && (
            <div className="space-y-3">
              {novels.length === 0 ? (
                <div className="text-center py-10 text-zinc-500 text-xs">
                  Chưa có bộ truyện nào. Hãy bấm các tab bên cạnh để nhập truyện mới!
                </div>
              ) : (
                novels.map((novel) => {
                  const isSelected = selectedNovelId === novel.id;
                  const isDeleting = deletingId === novel.id;
                  const isRenaming = editingNovelId === novel.id;
                  const isResplitting = resplittingId === novel.id;

                  return (
                    <div
                      key={novel.id}
                      onClick={() => onSelectNovel(novel)}
                      className={`p-3.5 rounded-xl border transition-all cursor-pointer flex items-center justify-between gap-4 ${
                        isSelected
                          ? "bg-amber-500/15 border-amber-500/50 shadow-md shadow-amber-500/10"
                          : "bg-zinc-900/60 border-zinc-800 hover:border-zinc-700 hover:bg-zinc-900"
                      }`}
                    >
                      <div className="space-y-1 flex-1">
                        <div className="flex items-center gap-2">
                          {isRenaming ? (
                            <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                              <Input
                                value={editingNovelName}
                                onChange={(e) => setEditingNovelName(e.target.value)}
                                className="h-7 text-xs bg-zinc-950 border-amber-500 w-64"
                                autoFocus
                              />
                              <Button
                                size="sm"
                                onClick={() => handleSaveRename(novel.id)}
                                className="h-7 px-2 bg-emerald-500 text-zinc-950 hover:bg-emerald-600"
                              >
                                <Check className="w-3.5 h-3.5" />
                              </Button>
                            </div>
                          ) : (
                            <>
                              <h4 className="text-sm font-bold text-white">{novel.name}</h4>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setEditingNovelId(novel.id);
                                  setEditingNovelName(novel.name);
                                }}
                                className="h-6 w-6 p-0 text-zinc-500 hover:text-amber-400"
                                title="Đổi tên bộ truyện"
                              >
                                <Edit3 className="w-3 h-3" />
                              </Button>
                            </>
                          )}

                          <Badge className="bg-amber-500/20 text-amber-300 border-amber-500/30 text-[10px] font-mono">
                            {novel.chapters_count?.toLocaleString() || 0} Chương
                          </Badge>
                          {isSelected && (
                            <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30 text-[10px]">
                              Đang Dùng
                            </Badge>
                          )}
                        </div>
                        <p className="text-[11px] font-mono text-zinc-500 truncate max-w-md">
                          📂 {novel.path}
                        </p>
                      </div>

                      <div className="flex items-center gap-2">
                        {/* Nút Tách lại chương & Lập Search Keys */}
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={(e) => handleResplitNovel(novel, e)}
                          disabled={isResplitting}
                          className="h-7 px-2 text-xs font-medium text-amber-400 hover:bg-amber-500/15 rounded-lg border border-amber-500/30"
                          title="Tách lại chương thông minh & cập nhật Search Keys"
                        >
                          <Wand2 className={`w-3.5 h-3.5 mr-1 ${isResplitting ? "animate-spin" : ""}`} />
                          Tách Lại ({novel.chapters_count})
                        </Button>

                        {/* Nút Đọc & Sửa Chương */}
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={(e) => handleOpenChapterEditor(novel, e)}
                          className="h-7 px-2.5 text-xs font-medium border-zinc-700 bg-zinc-800 hover:bg-zinc-700 text-zinc-200"
                        >
                          <BookText className="w-3.5 h-3.5 mr-1 text-amber-400" /> Sửa Chương
                        </Button>

                        <Button
                          size="sm"
                          variant={isSelected ? "default" : "outline"}
                          className={`h-7 text-xs font-semibold rounded-lg ${
                            isSelected
                              ? "bg-amber-500 text-zinc-950 font-bold"
                              : "border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                          }`}
                        >
                          {isSelected ? "Đã Chọn" : "Chọn Dùng"}
                        </Button>

                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={(e) => handleDeleteNovel(novel, e)}
                          disabled={isDeleting}
                          className="h-7 w-7 p-0 text-zinc-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg"
                          title="Xóa bộ truyện này"
                        >
                          {isDeleting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                        </Button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          )}

          {/* TAB: TRÌNH ĐỌC & SỬA NỘI DUNG CHƯƠNG KÈM SEARCH KEYS */}
          {activeTab === "editor" && (
            <div className="grid grid-cols-1 md:grid-cols-12 gap-4 h-[390px]">
              {/* Cột Trái: Danh sách chương & Search Keys */}
              <div className="md:col-span-4 border border-zinc-800 rounded-xl bg-zinc-950/60 p-2.5 flex flex-col space-y-2 h-full">
                <div className="relative">
                  <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-zinc-500" />
                  <Input
                    value={chapterSearch}
                    onChange={(e) => setChapterSearch(e.target.value)}
                    placeholder="Tìm số chương, tiêu đề, từ khóa..."
                    className="h-8 pl-8 text-xs bg-zinc-900 border-zinc-800"
                  />
                </div>

                <div className="flex-1 overflow-y-auto space-y-1 pr-1">
                  {filteredChapters.length === 0 ? (
                    <div className="text-center py-8 text-zinc-500 text-xs">Không tìm thấy chương nào</div>
                  ) : (
                    filteredChapters.map((c) => {
                      const isChSelected = selectedChapter?.filename === c.filename;
                      return (
                        <div
                          key={c.filename}
                          onClick={() => editingNovel && handleSelectChapter(editingNovel.id, c)}
                          className={`p-2 rounded-lg text-xs font-mono transition-all cursor-pointer space-y-0.5 ${
                            isChSelected
                              ? "bg-amber-500 text-zinc-950 font-bold"
                              : "text-zinc-300 hover:bg-zinc-900"
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="truncate flex-1">{c.title}</span>
                            {c.chapter_num && (
                              <span className={`text-[10px] ml-1 px-1 rounded ${isChSelected ? "bg-zinc-950/30 text-zinc-950" : "bg-zinc-800 text-amber-400"}`}>
                                #{c.chapter_num}
                              </span>
                            )}
                          </div>
                          {c.search_keys && c.search_keys.length > 0 && (
                            <div className="text-[10px] text-zinc-500 truncate flex items-center gap-1">
                              <Tag className="w-2.5 h-2.5" />
                              {c.search_keys.slice(0, 3).join(", ")}
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              </div>

              {/* Cột Phải: Khung soạn thảo văn bản chương & Search Keys Tag Bar */}
              <div className="md:col-span-8 border border-zinc-800 rounded-xl bg-zinc-950/60 p-3 flex flex-col space-y-2 h-full">
                <div className="flex items-center justify-between pb-1 border-b border-zinc-800">
                  <div className="font-bold text-xs text-amber-300 truncate max-w-sm">
                    {selectedChapter ? `📝 ${selectedChapter.title}` : "Chọn một chương để chỉnh sửa"}
                  </div>
                  {selectedChapter && (
                    <Button
                      size="sm"
                      onClick={handleSaveChapter}
                      disabled={savingChapter}
                      className="h-7 text-xs bg-amber-500 hover:bg-amber-600 text-zinc-950 font-bold px-3 rounded-lg"
                    >
                      {savingChapter ? <RefreshCw className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Save className="w-3.5 h-3.5 mr-1" />}
                      Lưu Thay Đổi
                    </Button>
                  )}
                </div>

                {/* Search Keys Chips */}
                {selectedChapter?.search_keys && selectedChapter.search_keys.length > 0 && (
                  <div className="flex items-center gap-1.5 overflow-x-auto py-1 text-[11px] font-mono text-zinc-400">
                    <span className="text-zinc-500 font-sans flex items-center gap-1"><Tag className="w-3 h-3 text-amber-400" /> Search Keys:</span>
                    {selectedChapter.search_keys.map((k, i) => (
                      <span key={i} className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-amber-300 text-[10px]">
                        {k}
                      </span>
                    ))}
                  </div>
                )}

                <textarea
                  value={chapterContent}
                  onChange={(e) => setChapterContent(e.target.value)}
                  disabled={!selectedChapter || loadingChapter}
                  className="flex-1 w-full p-2.5 rounded-lg bg-zinc-900 border border-zinc-800 text-xs text-zinc-200 font-mono leading-relaxed outline-none focus:border-amber-500 resize-none"
                  placeholder="Nội dung văn bản chương truyện..."
                />
              </div>
            </div>
          )}

          {/* TAB 2: Nhập từ 1 hoặc Nhiều File */}
          {activeTab === "files" && (
            <div className="space-y-4 p-2">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-200">Tên Bộ Truyện</label>
                <Input
                  value={novelName}
                  onChange={(e) => setNovelName(e.target.value)}
                  placeholder="Ví dụ: Phàm Nhân Tu Tiên, Thôn Phệ Tinh Không..."
                  className="bg-zinc-900 border-zinc-800 text-xs"
                />
              </div>

              {/* Upload Dropzone */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-200">Chọn 1 Hoặc Nhiều File Chương (.txt, .md)</label>
                <input
                  type="file"
                  multiple
                  accept=".txt,.md,.epub"
                  ref={fileInputRef}
                  onChange={handleFileChange}
                  className="hidden"
                />
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="p-6 rounded-2xl border-2 border-dashed border-zinc-700 hover:border-amber-500/60 bg-zinc-900/40 hover:bg-zinc-900/70 text-center cursor-pointer transition-all space-y-2"
                >
                  <div className="w-12 h-12 rounded-2xl bg-amber-500/15 border border-amber-500/30 flex items-center justify-center text-amber-400 mx-auto">
                    <Upload className="w-6 h-6" />
                  </div>
                  <div>
                    <p className="text-xs font-bold text-zinc-200">
                      Bấm vào đây để chọn 1 hoặc nhiều file từ máy tính
                    </p>
                    <p className="text-[11px] text-zinc-400 mt-0.5">
                      Hỗ trợ: 1 file Full dài (tự động chia chương & tạo Search Keys) hoặc nhiều file chương lẻ (001.txt, 002.txt...)
                    </p>
                  </div>
                </div>
              </div>

              {/* Selected Files Badge & List */}
              {selectedFiles.length > 0 && (
                <div className="p-3 rounded-xl bg-zinc-900 border border-zinc-800 space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-amber-300 flex items-center gap-1.5">
                      <FileCheck className="w-4 h-4 text-emerald-400" />
                      Đã chọn {selectedFiles.length} file
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setSelectedFiles([])}
                      className="h-6 text-[11px] text-zinc-400 hover:text-red-400 p-0"
                    >
                      Bỏ chọn tất cả
                    </Button>
                  </div>
                  <div className="max-h-24 overflow-y-auto space-y-1 text-[11px] font-mono text-zinc-400">
                    {selectedFiles.slice(0, 10).map((f, i) => (
                      <div key={i} className="truncate">• {f.name} ({(f.size / 1024).toFixed(1)} KB)</div>
                    ))}
                    {selectedFiles.length > 10 && (
                      <div className="text-zinc-500 italic">...và {selectedFiles.length - 10} file khác</div>
                    )}
                  </div>
                </div>
              )}

              <Button
                onClick={handleImportFiles}
                disabled={isSubmitting || selectedFiles.length === 0}
                className="w-full bg-amber-500 hover:bg-amber-600 text-zinc-950 font-bold text-xs h-9 rounded-xl shadow-lg shadow-amber-500/20"
              >
                {isSubmitting ? (
                  <>
                    <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                    Đang Đọc & Phân Tách Chương Thông Minh...
                  </>
                ) : (
                  <>
                    <Upload className="w-4 h-4 mr-2" />
                    Tải Lên & Nhập Vào Kho Truyện ({selectedFiles.length} file)
                  </>
                )}
              </Button>
            </div>
          )}

          {/* TAB 3: Nhập từ thư mục */}
          {activeTab === "folder" && (
            <div className="space-y-4 p-2">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-200">Tên Bộ Truyện</label>
                <Input
                  value={novelName}
                  onChange={(e) => setNovelName(e.target.value)}
                  placeholder="Ví dụ: Phàm Nhân Tu Tiên, Già Thiên..."
                  className="bg-zinc-900 border-zinc-800 text-xs"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-200">Đường Dẫn Thư Mục Chứa Các File Chương (.txt, .md)</label>
                <Input
                  value={folderPath}
                  onChange={(e) => setFolderPath(e.target.value)}
                  placeholder="C:\Users\...\Downloads\PhamNhanTuTien_Chapters"
                  className="bg-zinc-900 border-zinc-800 text-xs font-mono"
                />
                <p className="text-[11px] text-zinc-500">
                  Hệ thống sẽ quét toàn bộ các file văn bản trong thư mục và lập chỉ mục chương tự động.
                </p>
              </div>

              <Button
                onClick={handleImportFolder}
                disabled={isSubmitting}
                className="w-full bg-amber-500 hover:bg-amber-600 text-zinc-950 font-bold text-xs h-9 rounded-xl"
              >
                {isSubmitting ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <FolderPlus className="w-4 h-4 mr-2" />}
                Xác Nhận Nhập Thư Mục Truyện
              </Button>
            </div>
          )}

          {/* TAB 4: Nhập từ Link URL */}
          {activeTab === "url" && (
            <div className="space-y-4 p-2">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-200">Tên Bộ Truyện (Tùy chọn)</label>
                <Input
                  value={novelName}
                  onChange={(e) => setNovelName(e.target.value)}
                  placeholder="Để trống nếu muốn AI tự nhận diện từ tiêu đề web"
                  className="bg-zinc-900 border-zinc-800 text-xs"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-200">Link Web Truyện / URL</label>
                <Input
                  value={webUrl}
                  onChange={(e) => setWebUrl(e.target.value)}
                  placeholder="https://truyenfull.vn/... hoặc link đọc truyện"
                  className="bg-zinc-900 border-zinc-800 text-xs font-mono"
                />
              </div>

              <Button
                onClick={handleImportUrl}
                disabled={isSubmitting}
                className="w-full bg-amber-500 hover:bg-amber-600 text-zinc-950 font-bold text-xs h-9 rounded-xl"
              >
                {isSubmitting ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Globe className="w-4 h-4 mr-2" />}
                Cào Dữ Liệu & Nhập Tự Động
              </Button>
            </div>
          )}

        </div>

        {/* Footer */}
        <div className="p-3 px-5 border-t border-zinc-800/80 bg-zinc-950/80 flex items-center justify-end">
          <Button
            size="sm"
            onClick={() => onOpenChange(false)}
            className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-semibold rounded-xl"
          >
            Đóng
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};
