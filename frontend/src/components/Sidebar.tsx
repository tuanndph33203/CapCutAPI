import React from "react";
import {
  Folder,
  PlaySquare,
  Share2,
  Settings,
  Plug,
  Power,
  Zap,
  Bot,
  Info,
} from "lucide-react";
import { Button } from "./ui/button";
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
  SidebarRail,
  useSidebar,
} from "./ui/sidebar";

export type AdminRoute =
  | "projects"
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
  autoShutdown,
  isTestingConnection,
  onTestConnection,
  onToggleAutoShutdown,
}) => {
  const { state } = useSidebar();
  const isCollapsed = state === "collapsed";

  const mainNavItems = [
    {
      id: "projects",
      label: "Projects",
      icon: Folder,
    },
    {
      id: "queue",
      label: "Queue & Logs",
      icon: PlaySquare,
    },
    {
      id: "social_providers",
      label: "Social Providers",
      icon: Share2,
    },
    {
      id: "ai_providers",
      label: "AI Providers",
      icon: Bot,
    },
  ];

  const systemNavItems = [
    {
      id: "system_settings",
      label: "Settings",
      icon: Settings,
    },
  ];

  return (
    <ShadcnSidebar collapsible="icon" className="dark:bg-[#09090b]">
      {/* Brand Header */}
      <SidebarHeader className="h-16 flex justify-center border-b border-zinc-800 px-2 group-data-[collapsible=icon]:p-0 group-data-[collapsible=icon]:items-center">
        <SidebarMenu>
          <SidebarMenuItem className="flex justify-center">
            <SidebarMenuButton size="lg" className="hover:bg-zinc-800/60 transition-colors justify-center">
              <div className="aspect-square size-8 rounded-lg bg-zinc-800 border border-zinc-700 flex items-center justify-center text-zinc-100 shrink-0">
                <Zap className="w-4 h-4 text-zinc-100" />
              </div>
              <div className="grid flex-1 text-left text-xs leading-tight group-data-[collapsible=icon]:hidden">
                <span className="truncate font-bold text-zinc-100 text-sm">CapCut Studio</span>
                <span className="truncate text-[10px] text-zinc-400 font-medium">
                  Endpoint Proxy v2.5
                </span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent className="px-2 py-4 space-y-3 group-data-[collapsible=icon]:px-1 group-data-[collapsible=icon]:items-center">
        {/* Selected Project Indicator Banner */}
        {selectedProjectFolder && !isCollapsed && (
          <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800 text-xs space-y-1 mx-1">
            <span className="text-[10px] text-zinc-400 font-semibold uppercase tracking-wider block">
              Current Project:
            </span>
            <div className="flex items-center justify-between">
              <strong className="text-zinc-200 font-mono text-xs truncate">
                {selectedProjectFolder}
              </strong>
              <button
                onClick={onDeselectProject}
                className="text-[10px] text-zinc-400 hover:text-zinc-100 underline ml-2"
              >
                Close
              </button>
            </div>
          </div>
        )}

        {/* MAIN Group */}
        <SidebarGroup className="group-data-[collapsible=icon]:p-0 group-data-[collapsible=icon]:items-center">
          <SidebarGroupLabel className="text-zinc-500 font-semibold px-2">MAIN</SidebarGroupLabel>
          <SidebarMenu className="group-data-[collapsible=icon]:items-center">
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
                    className={`text-xs rounded-md transition-colors ${
                      isActive
                        ? "bg-zinc-800 text-white font-semibold"
                        : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
                    }`}
                  >
                    <Icon className="w-4 h-4 shrink-0" />
                    <span>{item.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarGroup>

        {/* SYSTEM Group */}
        <SidebarGroup className="group-data-[collapsible=icon]:p-0 group-data-[collapsible=icon]:items-center">
          <SidebarGroupLabel className="text-zinc-500 font-semibold px-2">SYSTEM</SidebarGroupLabel>
          <SidebarMenu className="group-data-[collapsible=icon]:items-center">
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
                    className={`text-xs rounded-md transition-colors ${
                      isActive
                        ? "bg-zinc-800 text-white font-semibold"
                        : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
                    }`}
                  >
                    <Icon className="w-4 h-4 shrink-0" />
                    <span>{item.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      {/* Bottom Status Card */}
      <SidebarFooter className="border-t border-zinc-800 p-3 group-data-[collapsible=icon]:p-1.5 group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:justify-center">
        {!isCollapsed ? (
          <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800 text-xs space-y-2">
            <div className="flex items-start gap-2 text-zinc-400">
              <Info className="w-4 h-4 text-zinc-400 shrink-0 mt-0.5" />
              <p className="text-[11px] leading-snug">
                Status:{" "}
                <strong className={isConnected ? "text-emerald-400" : "text-red-400"}>
                  {isConnected ? "Active" : "Offline"}
                </strong>
              </p>
            </div>

            <Button
              variant={autoShutdown ? "destructive" : "outline"}
              size="sm"
              onClick={onToggleAutoShutdown}
              className="w-full h-7 text-[11px] font-medium border-zinc-800 bg-zinc-950 text-zinc-300 hover:bg-zinc-800"
            >
              <Power className="w-3 h-3 mr-1" />
              <span>{autoShutdown ? "Shutdown Enabled" : "Shutdown"}</span>
            </Button>
          </div>
        ) : (
          <Button
            variant="ghost"
            size="icon"
            onClick={onTestConnection}
            disabled={isTestingConnection}
            title="Test Connection"
            className="size-9 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-800 flex items-center justify-center mx-auto p-0 shrink-0"
          >
            <Plug className="w-4 h-4" />
          </Button>
        )}
      </SidebarFooter>
      <SidebarRail />
    </ShadcnSidebar>
  );
};
