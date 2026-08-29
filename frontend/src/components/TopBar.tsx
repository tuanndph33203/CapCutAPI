import React from "react";
import { Plug, Power, Globe, Settings } from "lucide-react";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { SidebarTrigger } from "./ui/sidebar";
import { Separator } from "./ui/separator";

interface TopBarProps {
  isConnected: boolean;
  autoShutdown: boolean;
  isTestingConnection: boolean;
  onTestConnection: () => void;
  onToggleAutoShutdown: () => void;
  onOpenSocialModal: () => void;
  onOpenSettingsModal: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  isConnected,
  autoShutdown,
  isTestingConnection,
  onTestConnection,
  onToggleAutoShutdown,
  onOpenSocialModal,
  onOpenSettingsModal,
}) => {
  return (
    <header className="sticky top-0 z-20 w-full flex h-16 items-center justify-between px-6 bg-[#09090b]/80 backdrop-blur-xl border-b border-zinc-800/80">
      {/* Left Title & Status */}
      <div className="flex items-center gap-3.5">
        <SidebarTrigger className="text-zinc-400 hover:text-white" />
        <Separator orientation="vertical" className="h-4 bg-zinc-800" />
        <div className="flex items-center gap-2.5">
          <Badge
            variant="outline"
            className={`px-3 py-1 flex items-center gap-2 text-xs font-semibold rounded-full border transition-all ${
              isConnected
                ? "border-emerald-500/30 text-emerald-400 bg-emerald-500/10 shadow-sm shadow-emerald-500/10"
                : "border-amber-500/30 text-amber-400 bg-amber-500/10"
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                isConnected ? "bg-emerald-400 animate-pulse shadow-sm shadow-emerald-400" : "bg-amber-400"
              }`}
            />
            <span>{isConnected ? "CapCut Core Active" : "Waiting for Server"}</span>
          </Badge>
        </div>
      </div>

      {/* Right Controls */}
      <div className="flex items-center gap-2.5">
        <Button
          variant="outline"
          size="sm"
          onClick={onTestConnection}
          disabled={isTestingConnection}
          className="h-8 text-xs font-medium border-zinc-800 bg-zinc-900/60 hover:bg-zinc-800 hover:border-zinc-700 text-zinc-300 transition-all gap-1.5"
        >
          <Plug className="w-3.5 h-3.5 text-purple-400" />
          <span>{isTestingConnection ? "Đang kiểm tra..." : "Test CapCut UI"}</span>
        </Button>

        <Button
          variant="outline"
          size="sm"
          onClick={onOpenSocialModal}
          className="h-8 text-xs font-medium border-blue-500/30 bg-blue-950/30 hover:bg-blue-900/40 text-blue-300 transition-all gap-1.5"
        >
          <Globe className="w-3.5 h-3.5 text-blue-400" />
          <span>Social Hub</span>
        </Button>

        <Button
          variant="outline"
          size="sm"
          onClick={onOpenSettingsModal}
          className="h-8 text-xs font-medium border-zinc-800 bg-zinc-900/60 hover:bg-zinc-800 text-zinc-300 transition-all gap-1.5"
        >
          <Settings className="w-3.5 h-3.5 text-zinc-400" />
          <span>Cấu Hình</span>
        </Button>

        <Button
          variant={autoShutdown ? "destructive" : "outline"}
          size="sm"
          onClick={onToggleAutoShutdown}
          className={`h-8 text-xs font-medium transition-all gap-1.5 ${
            autoShutdown
              ? "bg-red-600 hover:bg-red-700 text-white shadow-sm shadow-red-600/20"
              : "border-zinc-800 bg-zinc-900/60 hover:bg-zinc-800 text-zinc-400"
          }`}
        >
          <Power className="w-3.5 h-3.5" />
          <span>{autoShutdown ? "Tắt máy: BẬT" : "Tắt máy: Tắt"}</span>
        </Button>
      </div>
    </header>
  );
};
