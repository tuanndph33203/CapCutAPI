import React, { useState, useEffect } from "react";
import { toast } from "sonner";
import { Plus, RefreshCw, Folder, Play, Video, Clock, Trash2 } from "lucide-react";
import { fetchPipelineProjects, createPipelineProject, runProjectPipeline, api, type PipelineProject } from "../lib/api";
import { Button } from "./ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "./ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/dialog";
import { Input } from "./ui/input";

interface ProjectGridProps {
  onSelectProject: (folder: string) => void;
}

export const ProjectGrid: React.FC<ProjectGridProps> = ({ onSelectProject }) => {
  const [projects, setProjects] = useState<PipelineProject[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [newProjectName, setNewProjectName] = useState<string>("");
  const [isCreating, setIsCreating] = useState<boolean>(false);

  const loadProjects = async () => {
    setLoading(true);
    try {
      const data = await fetchPipelineProjects();
      setProjects(data);
    } catch (err) {
      console.error("Lỗi tải danh sách dự án", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
  }, []);

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;

    setIsCreating(true);
    try {
      const res = await createPipelineProject(newProjectName.trim());
      if (res.ok) {
        setIsModalOpen(false);
        setNewProjectName("");
        await loadProjects();
        toast.success(`Đã tạo dự án thành công!`);
        if (res.folder) {
          onSelectProject(res.folder);
        }
      } else {
        toast.error("Lỗi tạo dự án", { description: res.error || "Không xác định" });
      }
    } catch (err: any) {
      toast.error("Lỗi tạo dự án", { description: err.message || String(err) });
    } finally {
      setIsCreating(false);
    }
  };

  const handleQuickRun = async (e: React.MouseEvent, folder: string) => {
    e.stopPropagation();
    try {
      const res = await runProjectPipeline(folder);
      if (res.ok) {
        toast.success(`Đã thêm dự án "${folder}" vào hàng chờ xử lý!`);
      } else {
        toast.error("Lỗi thêm vào hàng chờ", { description: res.error || "Không xác định" });
      }
    } catch (err: any) {
      toast.error("Lỗi gọi API", { description: err.message || String(err) });
    }
  };

  const handleDeleteProject = async (e: React.MouseEvent, folder: string, name: string) => {
    e.stopPropagation();
    if (!window.confirm(`Bạn có chắc chắn muốn xóa dự án "${name || folder}"?`)) return;
    try {
      const res = await api.delete(`/pipeline-projects/${encodeURIComponent(folder)}`);
      if (res.data?.ok) {
        toast.success(`Đã xóa dự án "${name || folder}"`);
        await loadProjects();
      } else {
        toast.error("Lỗi khi xóa", { description: res.data?.error || "Không thể xóa dự án" });
      }
    } catch (err: any) {
      toast.error("Lỗi khi xóa dự án", { description: err.message || String(err) });
    }
  };

  return (
    <div className="space-y-6">
      {/* Section Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-extrabold text-foreground">Projects</h2>
          <p className="text-xs text-muted-foreground">
            Danh sách các thư mục dự án sản xuất video
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={loadProjects}
            disabled={loading}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Làm mới</span>
          </Button>

          <Button
            variant="default"
            size="sm"
            onClick={() => setIsModalOpen(true)}
          >
            <Plus className="w-4 h-4" />
            <span>Tạo mới</span>
          </Button>
        </div>
      </div>

      {/* Grid Container */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="animate-pulse h-48 bg-card/30" />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <Card className="p-12 text-center flex flex-col items-center justify-center gap-4">
          <Folder className="w-16 h-16 text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground">
            Chưa có dự án nào. Bấm <strong className="text-cyan-400">+ Tạo mới</strong> để bắt đầu.
          </p>
          <Button variant="default" size="sm" onClick={() => setIsModalOpen(true)}>
            <Plus className="w-4 h-4" /> Tạo dự án đầu tiên
          </Button>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {projects.map((proj) => (
            <Card
              key={proj.Folder}
              onClick={() => onSelectProject(proj.Folder)}
              className="group cursor-pointer hover:border-cyan-500/50 hover:shadow-cyan-500/10 hover:-translate-y-1 relative overflow-hidden"
            >
              <CardHeader className="p-4 pb-2">
                <CardTitle className="group-hover:text-cyan-400 transition-colors flex items-center justify-between text-base">
                  <span className="truncate">{proj.ProjectName || proj.Folder}</span>
                  <Folder className="w-4 h-4 text-cyan-400 shrink-0" />
                </CardTitle>
                <CardDescription className="font-mono text-[11px]">
                  Folder: {proj.Folder}
                </CardDescription>
              </CardHeader>

              <CardContent className="p-4 pt-2">
                <div className="flex items-center gap-4 text-xs text-muted-foreground font-mono">
                  <div className="flex items-center gap-1">
                    <Video className="w-3.5 h-3.5 text-cyan-400" />
                    <span>{proj.TotalVideos || 0} videos</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Clock className="w-3.5 h-3.5 text-purple-400" />
                    <span>{proj.DurationSec || 0}s</span>
                  </div>
                </div>
              </CardContent>

              <CardFooter className="p-4 pt-2 flex items-center justify-between">
                <Button variant="link" size="sm" className="p-0 text-cyan-400">
                  Xem chi tiết &rarr;
                </Button>

                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => handleDeleteProject(e, proj.Folder, proj.ProjectName)}
                    className="h-8 px-2 text-zinc-400 hover:text-red-400 hover:bg-red-500/10"
                    title="Xóa dự án"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>

                  <Button
                    variant="default"
                    size="sm"
                    onClick={(e) => handleQuickRun(e, proj.Folder)}
                  >
                    <Play className="w-3 h-3 fill-current mr-1" /> Chạy
                  </Button>
                </div>
              </CardFooter>
            </Card>
          ))}
        </div>
      )}

      {/* Create Project Modal using Shadcn UI Dialog */}
      <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>📂 Tạo Pipeline Project mới</DialogTitle>
            <DialogDescription>
              Đặt tên cho dự án. Cấu hình chi tiết (video, phụ đề, AI...) có thể chỉnh sau khi tạo.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleCreateProject} className="space-y-4 py-2">
            <div>
              <label className="block text-xs font-semibold text-muted-foreground mb-1">
                Tên dự án mới (Folder ID):
              </label>
              <Input
                type="text"
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
                placeholder="Ví dụ: Hoang_Anh_178"
                autoFocus
              />
            </div>

            <DialogFooter>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => setIsModalOpen(false)}
              >
                Hủy
              </Button>
              <Button
                type="submit"
                variant="default"
                size="sm"
                disabled={isCreating || !newProjectName.trim()}
              >
                {isCreating ? "Đang tạo..." : "Tạo dự án"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
};
