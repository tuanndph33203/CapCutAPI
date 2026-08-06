import React, { useState, useEffect, useRef } from "react";
import { toast } from "sonner";
import { Play, Pause, PlayCircle, Trash2, Cpu, HardDrive, Terminal, Filter, RotateCcw, XCircle, Copy, Eraser } from "lucide-react";
import {
  fetchSystemStatus,
  startQueue,
  pauseQueue,
  resumeQueue,
  clearQueue,
  deleteQueueItem,
  retryQueueItem,
  cancelQueueItem,
  type SystemStatus,
  type QueueItem,
} from "../lib/api";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Badge } from "./ui/badge";

export const QueueAndLogs: React.FC = () => {
  const [statusData, setStatusData] = useState<SystemStatus | null>(null);
  const [filter, setFilter] = useState<string>("active");
  const [logs, setLogs] = useState<string[]>([
    "[Hệ thống] Đang kết nối tới máy chủ CapCut Automation Studio...",
    "[Hệ thống] Chào mừng đến với bảng điều khiển Automation trực tiếp!",
  ]);
  const logEndRef = useRef<HTMLDivElement>(null);

  const loadStatus = async () => {
    try {
      const data = await fetchSystemStatus();
      setStatusData(data);
      if (data && Array.isArray(data.queue)) {
        data.queue.forEach((item: any) => {
          if (item.status === "failed" && item.message) {
            const errLog = `[LỖI PIPELINE] ${item.video || item.project_name || item.folder || "Dự án"}: ${item.message}`;
            setLogs((prev) => {
              if (!prev.includes(errLog)) {
                return [...prev.slice(-300), errLog];
              }
              return prev;
            });
          }
        });
      }
    } catch (err) {
      console.error("Lỗi lấy trạng thái hàng chờ", err);
    }
  };

  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, 2000);

    let eventSource: EventSource | null = null;
    try {
      eventSource = new EventSource("/api/logs");
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.message) {
            const level = data.level || "info";
            const timeStr = new Date().toLocaleTimeString("vi-VN");
            setLogs((prev) => [
              ...prev.slice(-300),
              `[${timeStr}] [${level.toUpperCase()}] ${data.message}`,
            ]);
          }
        } catch (err) {}
      };
    } catch (e) {
      console.warn("Lỗi tạo SSE logs:", e);
    }

    return () => {
      clearInterval(interval);
      if (eventSource) eventSource.close();
    };
  }, []);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const handleAction = async (actionFn: () => Promise<any>, successMsg: string) => {
    try {
      await actionFn();
      await loadStatus();
      setLogs((prev) => [...prev, `[Hệ thống] ${successMsg}`]);
      toast.success(successMsg);
    } catch (err: any) {
      toast.error("Lỗi thao tác hàng chờ", { description: err.message || String(err) });
    }
  };

  const queue = statusData?.queue || [];
  const filteredQueue = queue.filter((item: QueueItem) => {
    if (filter === "running") return item.status === "running";
    if (filter === "pending") return item.status === "pending";
    if (filter === "failed") return item.status === "failed";
    if (filter === "success") return item.status === "success";
    return true;
  });

  const bufferA = statusData?.buffer_status?.["00000000000"] || { occupied: false, owner_status: "free" };
  const bufferB = statusData?.buffer_status?.["111111111111111111"] || { occupied: false, owner_status: "free" };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mt-10">
      {/* Left: Queue Panel using Shadcn UI Card (7 Cols) */}
      <Card className="lg:col-span-7 flex flex-col justify-between p-6">
        <div>
          {/* Header & Controls */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 mb-4 border-b border-white/10">
            <h2 className="text-lg font-bold text-cyan-400">Hàng chờ Automation</h2>
            <div className="flex items-center gap-2 flex-wrap">
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleAction(startQueue, "Đã bấm Chạy hàng chờ")}
                className="border-cyan-500/30 text-cyan-300 hover:bg-cyan-500/20"
              >
                <Play className="w-3.5 h-3.5" /> Chạy
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleAction(pauseQueue, "Đã bấm Tạm dừng hàng chờ")}
                className="border-amber-500/30 text-amber-300 hover:bg-amber-500/20"
              >
                <Pause className="w-3.5 h-3.5" /> Tạm dừng
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleAction(resumeQueue, "Đã bấm Tiếp tục hàng chờ")}
                className="border-purple-500/30 text-purple-300 hover:bg-purple-500/20"
              >
                <PlayCircle className="w-3.5 h-3.5" /> Tiếp tục
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => handleAction(clearQueue, "Đã xóa toàn bộ hàng chờ")}
              >
                <Trash2 className="w-3.5 h-3.5" /> Xóa hàng chờ
              </Button>
            </div>
          </div>

          {/* Diagnostics Panel */}
          <div className="p-3 rounded-xl bg-black/40 border border-white/10 text-xs mb-4 grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div className="flex items-center gap-2">
              <Cpu className="w-4 h-4 text-cyan-400" />
              <span>
                <strong>Workers:</strong> Preprocess:{" "}
                <span className="text-cyan-300 font-semibold">{statusData?.workers?.preprocess || "INACTIVE"}</span> | GUI:{" "}
                <span className="text-purple-300 font-semibold">{statusData?.workers?.gui || "INACTIVE"}</span>
              </span>
            </div>
            <div className="flex items-center gap-2">
              <HardDrive className="w-4 h-4 text-emerald-400" />
              <span>
                <strong>Buffers:</strong> A:{" "}
                <span className={bufferA.occupied ? "text-amber-400 font-semibold" : "text-emerald-400 font-semibold"}>
                  {bufferA.occupied ? "BUSY" : "FREE"}
                </span>{" "}
                | B:{" "}
                <span className={bufferB.occupied ? "text-amber-400 font-semibold" : "text-emerald-400 font-semibold"}>
                  {bufferB.occupied ? "BUSY" : "FREE"}
                </span>
              </span>
            </div>
          </div>

          {/* Filter Tabs */}
          <div className="flex items-center gap-2 mb-4 overflow-x-auto pb-1">
            <Filter className="w-3.5 h-3.5 text-muted-foreground mr-1" />
            {[
              { key: "active", label: "Tất cả" },
              { key: "running", label: "Đang chạy" },
              { key: "pending", label: "Chờ xử lý" },
              { key: "failed", label: "Lỗi" },
              { key: "success", label: "Hoàn thành" },
            ].map((t) => (
              <Button
                key={t.key}
                variant={filter === t.key ? "default" : "secondary"}
                size="sm"
                onClick={() => setFilter(t.key)}
                className="h-7 text-[11px] px-2.5"
              >
                {t.label}
              </Button>
            ))}
          </div>

          {/* Table */}
          <div className="overflow-x-auto border border-white/10 rounded-xl max-h-80 overflow-y-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead className="bg-black/60 sticky top-0 text-muted-foreground border-b border-white/10">
                <tr>
                  <th className="p-3 w-10">STT</th>
                  <th className="p-3">Dự án / Video</th>
                  <th className="p-3">Trạng thái</th>
                  <th className="p-3">Tiến trình</th>
                  <th className="p-3">Chi tiết / Thông báo</th>
                  <th className="p-3 text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {filteredQueue.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="text-center py-10 text-muted-foreground">
                      Hàng chờ trống. Vui lòng bấm nút chạy trên thẻ dự án để bắt đầu.
                    </td>
                  </tr>
                ) : (
                  filteredQueue.map((item, idx) => (
                    <tr key={idx} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                      <td className="p-3 font-mono">{idx + 1}</td>
                      <td className="p-3 font-semibold text-foreground truncate max-w-[160px]" title={item.video || item.project_name || item.folder}>
                        {item.project_name || item.video_name || item.folder || item.video || `Project ${idx + 1}`}
                      </td>
                      <td className="p-3">
                        <Badge
                          variant={
                            item.status === "running"
                              ? "default"
                              : item.status === "success"
                              ? "success"
                              : item.status === "failed"
                              ? "destructive"
                              : "secondary"
                          }
                        >
                          {item.status.toUpperCase()}
                        </Badge>
                      </td>
                      <td className="p-3">
                        <div className="w-full bg-black/40 rounded-full h-2 overflow-hidden border border-white/10">
                          <div
                            className="bg-cyan-400 h-full transition-all duration-300"
                            style={{ width: `${item.progress || 0}%` }}
                          />
                        </div>
                      </td>
                      <td className="p-3 max-w-[220px] truncate" title={item.message || ""}>
                        <span className={item.status === "failed" ? "text-red-400 font-semibold" : "text-muted-foreground"}>
                          {item.message || (item.status === "failed" ? "Lỗi tiến trình" : "—")}
                        </span>
                      </td>
                      <td className="p-3 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {item.status === "failed" && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() =>
                                handleAction(
                                  () => retryQueueItem(idx),
                                  `Đã xếp lại dự án thứ ${idx + 1} vào hàng chờ`
                                )
                              }
                              className="h-7 text-xs px-2 border-amber-500/40 text-amber-300 bg-amber-500/10 hover:bg-amber-500/20"
                              title="Thử lại"
                            >
                              <RotateCcw className="w-3.5 h-3.5 mr-1" /> Thử lại
                            </Button>
                          )}

                          {(item.status === "running" ||
                            item.status === "pending" ||
                            item.status === "preprocessing" ||
                            item.status === "gui_processing") && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() =>
                                handleAction(
                                  () => cancelQueueItem(idx),
                                  `Đã hủy dự án thứ ${idx + 1}`
                                )
                              }
                              className="h-7 text-xs px-2 border-red-500/40 text-red-300 bg-red-500/10 hover:bg-red-500/20"
                              title="Hủy"
                            >
                              <XCircle className="w-3.5 h-3.5 mr-1" /> Hủy
                            </Button>
                          )}

                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              handleAction(
                                () => deleteQueueItem(idx),
                                `Đã xóa mục thứ ${idx + 1} khỏi hàng chờ`
                              )
                            }
                            className="h-7 text-xs px-2 text-zinc-400 hover:text-red-400"
                            title="Xóa"
                          >
                            <Trash2 className="w-3.5 h-3.5 mr-1" /> Xóa
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </Card>

      {/* Right: Realtime Console Terminal Panel using Shadcn UI Card (5 Cols) */}
      <Card className="lg:col-span-5 flex flex-col justify-between bg-zinc-950/90 border-zinc-800 font-mono p-5 shadow-2xl">
        <div>
          <div className="flex items-center justify-between pb-3 mb-3 border-b border-zinc-800">
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-red-500/80 inline-block" />
              <span className="w-3 h-3 rounded-full bg-amber-500/80 inline-block" />
              <span className="w-3 h-3 rounded-full bg-emerald-500/80 inline-block" />
              <span className="text-xs font-bold text-zinc-300 ml-2 flex items-center gap-1.5 font-sans">
                <Terminal className="w-4 h-4 text-cyan-400" /> Log Tiến Trình trực tiếp
              </span>
            </div>

            <div className="flex items-center gap-1.5">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  navigator.clipboard.writeText(logs.join("\n"));
                  toast.success("Đã sao chép toàn bộ Logs!");
                }}
                className="h-6 text-[10px] px-2 text-zinc-400 hover:text-cyan-300"
                title="Sao chép Log"
              >
                <Copy className="w-3 h-3 mr-1" /> Copy
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setLogs(["[Hệ thống] Đã xóa lịch sử log hiển thị."]);
                  toast.info("Đã xóa log hiển thị");
                }}
                className="h-6 text-[10px] px-2 text-zinc-400 hover:text-amber-400"
                title="Xóa Log"
              >
                <Eraser className="w-3 h-3 mr-1" /> Clear
              </Button>
            </div>
          </div>

          <div className="h-80 overflow-y-auto space-y-1.5 text-xs leading-relaxed font-mono pr-2 scrollbar-thin">
            {logs.map((log, i) => {
              const isError = log.includes("[ERROR]") || log.includes("[LỖI]") || log.includes("LỖI");
              const isWarning = log.includes("[WARNING]") || log.includes("[WARN]") || log.includes("CẢNH BÁO");
              const isSuccess = log.includes("[SUCCESS]") || log.includes("HOÀN THÀNH") || log.includes("thành công");

              let styleClass = "text-zinc-200";
              if (isError) {
                styleClass = "text-red-400 font-bold bg-red-950/40 p-2 rounded border border-red-500/30 my-1 block";
              } else if (isWarning) {
                styleClass = "text-amber-300 font-semibold";
              } else if (isSuccess) {
                styleClass = "text-emerald-400 font-semibold";
              }

              return (
                <div key={i} className={`break-all ${styleClass}`}>
                  {log}
                </div>
              );
            })}
            <div ref={logEndRef} />
          </div>
        </div>
      </Card>
    </div>
  );
};
