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
    <header className="sticky top-0 z-20 w-full flex h-16 items-center justify-between px-6 bg-[#09090b]/90 backdrop-blur-md border-b border-zinc-800/80">
      {/* Left Title & Status */}
      <div className="flex items-center gap-3">
        <SidebarTrigger />
        <Separator orientation="vertical" className="h-4" />
        <div className="flex items-center gap-2">
          <Badge
            variant="outline"
            className={`px-2.5 py-1 flex items-center gap-1.5 text-xs font-semibold rounded-full ${
              isConnected
                ? "border-emerald-500/30 text-emerald-400 bg-emerald-500/10"
                : "border-red-500/30 text-red-400 bg-red-500/10"
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                isConnected ? "bg-emerald-400 animate-pulse" : "bg-red-500"
              }`}
            />
            <span>{isConnected ? "Server Active" : "Server Disconnected"}</span>
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
          className="h-8 text-xs font-medium border-zinc-700 bg-zinc-900/80 hover:bg-zinc-800 text-zinc-200"
        >
          <Plug className="w-3.5 h-3.5 mr-1.5 text-purple-400" />
          <span>{isTestingConnection ? "Testing..." : "Test Connection"}</span>
        </Button>

        <Button
          variant="outline"
          size="sm"
          onClick={onOpenSocialModal}
          className="h-8 text-xs font-medium border-zinc-700 bg-zinc-900/80 hover:bg-zinc-800 text-cyan-300"
        >
          <Globe className="w-3.5 h-3.5 mr-1.5 text-cyan-400" />
          <span>Social Network</span>
        </Button>

        <Button
          variant="outline"
          size="sm"
          onClick={onOpenSettingsModal}
          className="h-8 text-xs font-medium border-zinc-700 bg-zinc-900/80 hover:bg-zinc-800 text-zinc-200"
        >
          <Settings className="w-3.5 h-3.5 mr-1.5 text-zinc-400" />
          <span>Global Config</span>
        </Button>

        <Button
          variant={autoShutdown ? "destructive" : "outline"}
          size="sm"
          onClick={onToggleAutoShutdown}
          className="h-8 text-xs font-medium border-zinc-700 bg-zinc-900/80 text-zinc-200"
        >
          <Power className="w-3.5 h-3.5 mr-1.5" />
          <span>Shutdown: {autoShutdown ? "ON" : "OFF"}</span>
        </Button>
      </div>
    </header>
  );
};
