import React, { useState, useEffect } from "react";
import { Globe, Settings, Plug, Power } from "lucide-react";
import { fetchSystemStatus, testUIConnection, toggleAutoShutdown } from "../lib/api";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { toast } from "sonner";

interface HeaderProps {
  onOpenSocialModal: () => void;
  onOpenSettingsModal: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onOpenSocialModal, onOpenSettingsModal }) => {
  const [statusText, setStatusText] = useState<string>("Đang kết nối...");
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [autoShutdown, setAutoShutdown] = useState<boolean>(false);
  const [isTesting, setIsTesting] = useState<boolean>(false);

  useEffect(() => {
    const checkStatus = async () => {
      try {
        const data = await fetchSystemStatus();
        setIsConnected(true);
        setStatusText("Máy chủ Hoạt động");
        setAutoShutdown(data.auto_shutdown);
      } catch (err) {
        setIsConnected(false);
        setStatusText("Mất kết nối");
      }
    };
    checkStatus();
    const interval = setInterval(checkStatus, 4000);
    return () => clearInterval(interval);
  }, []);

  const handleTestConnection = async () => {
    setIsTesting(true);
    try {
      const res = await testUIConnection();
      if (res.ok) {
        toast.success(`Kết nối UI CapCut thành công!`, {
          description: `Cửa sổ: ${res.window || "CapCut"}`,
        });
      } else {
        const detail = res.message || res.error || "Không tìm thấy cửa sổ ứng dụng CapCut";
        const msg = detail.includes("not found") || detail.includes("CapCut window")
          ? "Chưa mở ứng dụng CapCut trên máy tính. Vui lòng bật ứng dụng CapCut và thử lại!"
          : detail;
        toast.error("Lỗi kết nối UI CapCut", { description: msg });
      }
    } catch (err: any) {
      toast.error("Lỗi gọi API", { description: err.response?.data?.error || err.message || String(err) });
    } finally {
      setIsTesting(false);
    }
  };

  const handleToggleAutoShutdown = async () => {
    try {
      const res = await toggleAutoShutdown();
      setAutoShutdown(res.auto_shutdown);
      toast.info(`Trạng thái Tắt máy: ${res.auto_shutdown ? "BẬT" : "Tắt"}`);
    } catch (err: any) {
      toast.error("Lỗi thay đổi trạng thái Tắt máy");
    }
  };

  return (
    <header className="sticky top-0 z-40 w-full backdrop-blur-xl bg-card/60 border-b border-white/10 px-6 py-4 mb-8">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Logo Section */}
        <div>
          <h1 className="text-2xl font-black tracking-tight bg-gradient-to-r from-cyan-400 via-purple-400 to-amber-400 bg-clip-text text-transparent">
            CapCut Automation Studio
          </h1>
          <p className="text-xs text-muted-foreground font-medium mt-0.5">
            Hệ thống tự động hóa sản xuất & dịch thuật từng dự án riêng biệt
          </p>
        </div>

        {/* Header Actions using Shadcn UI Button & Badge */}
        <div className="flex items-center flex-wrap gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={onOpenSocialModal}
            className="border-cyan-500/30 text-cyan-300 hover:bg-cyan-500/10"
          >
            <Globe className="w-3.5 h-3.5 text-cyan-400" />
            <span>Mạng xã hội</span>
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={onOpenSettingsModal}
          >
            <Settings className="w-3.5 h-3.5 text-muted-foreground" />
            <span>Settings</span>
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleTestConnection}
            disabled={isTesting}
          >
            <Plug className="w-3.5 h-3.5 text-purple-400" />
            <span>{isTesting ? "Testing..." : "Test connection"}</span>
          </Button>

          <Button
            variant={autoShutdown ? "destructive" : "secondary"}
            size="sm"
            onClick={handleToggleAutoShutdown}
          >
            <Power className="w-3.5 h-3.5" />
            <span>Tắt máy: {autoShutdown ? "BẬT" : "Tắt"}</span>
          </Button>

          {/* Status Badge using Shadcn UI Badge */}
          <Badge variant={isConnected ? "default" : "destructive"}>
            <span
              className={`w-2 h-2 rounded-full ${
                isConnected ? "bg-cyan-400 animate-pulse" : "bg-red-500"
              }`}
            />
            <span>{statusText}</span>
          </Badge>
        </div>
      </div>
    </header>
  );
};
