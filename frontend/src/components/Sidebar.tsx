import React from "react";
import {
  Folder,
  PlaySquare,
  Share2,
  Settings,
  Sparkles,
  Zap,
  Bot,
  Activity,
  BookOpen,
} from "lucide-react";
import {
  Sidebar as ShadcnSidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "./ui/sidebar";

export type AdminRoute =
  | "projects"
  | "novels"
  | "queue"
  | "social_providers"
  | "ai_providers"
  | "system_settings";

interface SidebarProps {
  currentRoute: AdminRoute;
  onNavigate: (route: AdminRoute) => void;
  selectedProjectFolder: string | null;
  onDeselectProject: () => void;
  isConnected: boolean;
  autoShutdown: boolean;
  isTestingConnection: boolean;
  onTestConnection: () => void;
  onToggleAutoShutdown: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentRoute,
  onNavigate,
  selectedProjectFolder,
  onDeselectProject,
  isConnected,
}) => {
  const { state } = useSidebar();
  const isCollapsed = state === "collapsed";

  const mainNavItems = [
    {
      id: "projects",
      label: "Dự Án Video (Projects)",
      icon: Folder,
      badge: "Pipeline",
    },
    {
      id: "novels",
      label: "Quản Lý Truyện & Kịch Bản",
      icon: BookOpen,
      badge: "AI Novel",
    },
    {
      id: "queue",
      label: "Hàng Đợi Render (Queue)",
      icon: PlaySquare,
      badge: "Live",
    },
    {
      id: "social_providers",
      label: "Social Hub (Đa Kênh)",
      icon: Share2,
      badge: "YouTube/TikTok",
    },
    {
      id: "ai_providers",
      label: "AI Profiles (OpenAI/Gemini)",
      icon: Bot,
      badge: "AI",
    },
  ];

  const systemNavItems = [
    {
      id: "system_settings",
      label: "Cài Đặt Hệ Thống",
      icon: Settings,
    },
  ];

  return (
    <ShadcnSidebar collapsible="icon" className="dark:bg-[#0c0c0e] border-r border-zinc-800/80">
      {/* Brand Header */}
      <SidebarHeader className="h-16 flex justify-center border-b border-zinc-800/80 px-3 group-data-[collapsible=icon]:p-0 group-data-[collapsible=icon]:items-center">
        <SidebarMenu>
          <SidebarMenuItem className="flex justify-center">
            <SidebarMenuButton size="lg" className="hover:bg-zinc-800/50 transition-all justify-center">
              <div className="aspect-square size-9 rounded-xl bg-gradient-to-br from-cyan-500 via-blue-600 to-purple-600 flex items-center justify-center text-white shadow-md shadow-blue-500/20 shrink-0">
                <Zap className="w-5 h-5 fill-white/20" />
              </div>
              <div className="grid flex-1 text-left text-xs leading-tight group-data-[collapsible=icon]:hidden pl-1">
                <span className="truncate font-extrabold text-zinc-100 text-sm tracking-tight flex items-center gap-1.5">
                  CapCut Studio
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-400 border border-blue-500/30">
                    Pro
                  </span>
                </span>
                <span className="truncate text-[10px] text-zinc-400 font-medium">
                  Automation & Social Publisher
                </span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent className="px-3 py-4 space-y-4 group-data-[collapsible=icon]:px-1 group-data-[collapsible=icon]:items-center">
        {/* Selected Project Indicator Banner */}
        {selectedProjectFolder && !isCollapsed && (
          <div className="p-3 rounded-xl bg-blue-950/30 border border-blue-500/30 text-xs space-y-1 mx-0.5 animate-in fade-in-50">
            <span className="text-[10px] text-blue-400 font-bold uppercase tracking-wider flex items-center gap-1">
              <Sparkles className="w-3 h-3" /> Đang chọn dự án:
            </span>
            <div className="flex items-center justify-between pt-0.5">
              <strong className="text-zinc-100 font-mono text-xs truncate">
                {selectedProjectFolder}
              </strong>
              <button
                onClick={onDeselectProject}
                className="text-[10px] text-zinc-400 hover:text-zinc-100 underline ml-2 shrink-0"
              >
                Đóng
              </button>
            </div>
          </div>
        )}

        {/* MAIN Group */}
        <SidebarGroup className="group-data-[collapsible=icon]:p-0 group-data-[collapsible=icon]:items-center">
          <SidebarGroupLabel className="text-zinc-500 font-bold text-[10px] tracking-wider px-2 uppercase">
            Quản Lý & Xuất Bản
          </SidebarGroupLabel>
          <SidebarMenu className="space-y-1 group-data-[collapsible=icon]:items-center">
            {mainNavItems.map((item) => {
              const Icon = item.icon;
              const isActive = !selectedProjectFolder && currentRoute === item.id;
              return (
                <SidebarMenuItem key={item.id} className="group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:justify-center">
                  <SidebarMenuButton
                    tooltip={item.label}
                    isActive={isActive}
                    onClick={() => {
                      onDeselectProject();
                      onNavigate(item.id as AdminRoute);
                    }}
                    className={`text-xs py-2.5 px-3 rounded-lg transition-all duration-200 ${
                      isActive
                        ? "bg-gradient-to-r from-blue-600/20 to-blue-500/10 text-white font-semibold border border-blue-500/30 shadow-sm"
                        : "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/40"
                    }`}
                  >
                    <Icon className={`w-4 h-4 shrink-0 ${isActive ? "text-blue-400" : "text-zinc-400"}`} />
                    <span className="flex-1 truncate">{item.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarGroup>

        {/* SYSTEM Group */}
        <SidebarGroup className="group-data-[collapsible=icon]:p-0 group-data-[collapsible=icon]:items-center">
          <SidebarGroupLabel className="text-zinc-500 font-bold text-[10px] tracking-wider px-2 uppercase">
            Hệ Thống
          </SidebarGroupLabel>
          <SidebarMenu className="space-y-1 group-data-[collapsible=icon]:items-center">
            {systemNavItems.map((item) => {
              const Icon = item.icon;
              const isActive = !selectedProjectFolder && currentRoute === item.id;
              return (
                <SidebarMenuItem key={item.id} className="group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:justify-center">
                  <SidebarMenuButton
                    tooltip={item.label}
                    isActive={isActive}
                    onClick={() => {
                      onDeselectProject();
                      onNavigate(item.id as AdminRoute);
                    }}
                    className={`text-xs py-2.5 px-3 rounded-lg transition-all duration-200 ${
                      isActive
                        ? "bg-gradient-to-r from-purple-600/20 to-purple-500/10 text-white font-semibold border border-purple-500/30 shadow-sm"
                        : "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/40"
                    }`}
                  >
                    <Icon className={`w-4 h-4 shrink-0 ${isActive ? "text-purple-400" : "text-zinc-400"}`} />
                    <span className="flex-1 truncate">{item.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      {/* Bottom Status Card */}
      <SidebarFooter className="border-t border-zinc-800/80 p-3 group-data-[collapsible=icon]:p-1.5 group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:justify-center">
        {!isCollapsed ? (
          <div className="p-3 rounded-xl bg-zinc-900/60 border border-zinc-800/80 text-xs space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold text-zinc-300 flex items-center gap-1.5">
                <Activity className="w-3.5 h-3.5 text-blue-400" /> Server Port 9001
              </span>
              <span className="flex h-2 w-2 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
            </div>
            <div className="text-[10px] text-zinc-400 flex items-center justify-between">
              <span>Trạng thái:</span>
              <span className={isConnected ? "text-emerald-400 font-medium" : "text-amber-400 font-medium"}>
                {isConnected ? "Trực tuyến (Online)" : "Chờ kết nối"}
              </span>
            </div>
          </div>
        ) : (
          <div className="flex h-3 w-3 relative justify-center items-center">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </div>
        )}
      </SidebarFooter>
    </ShadcnSidebar>
  );
};
