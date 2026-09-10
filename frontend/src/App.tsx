import { useState, useEffect } from "react";
import { Sidebar, type AdminRoute } from "./components/Sidebar";
import { SidebarProvider, SidebarInset } from "./components/ui/sidebar";
import { TopBar } from "./components/TopBar";
import { ProjectGrid } from "./components/ProjectGrid";
import { ProjectDetails } from "./components/ProjectDetails";
import { QueueAndLogs } from "./components/QueueAndLogs";
import { SocialProvidersPage } from "./components/SocialProvidersPage";
import { NovelsPage } from "./components/NovelsPage";
import { CloudDataPage } from "./components/CloudDataPage";
import { SystemSettingsModal } from "./components/SystemSettingsModal";
import { fetchSystemStatus, testUIConnection, toggleAutoShutdown } from "./lib/api";
import { ErrorBoundary } from "./components/ErrorBoundary";

import { toast } from "sonner";
import { Toaster } from "./components/ui/toaster";

export function App() {
  const [currentRoute, setCurrentRoute] = useState<AdminRoute>("projects");
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
  const [isSystemModalOpen, setIsSystemModalOpen] = useState<boolean>(false);

  // System State
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [autoShutdown, setAutoShutdown] = useState<boolean>(false);
  const [isTestingConnection, setIsTestingConnection] = useState<boolean>(false);

  useEffect(() => {
    const checkStatus = async () => {
      try {
        const data = await fetchSystemStatus();
        setIsConnected(true);
        setAutoShutdown(data.auto_shutdown);
      } catch (err) {
        setIsConnected(false);
      }
    };
    checkStatus();
    const interval = setInterval(checkStatus, 4000);
    return () => clearInterval(interval);
  }, []);

  const handleTestConnection = async () => {
    setIsTestingConnection(true);
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
      setIsTestingConnection(false);
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

  const handleSelectProject = (folder: string) => {
    setSelectedFolder(folder);
  };

  return (
    <SidebarProvider defaultOpen={true}>
      <div className="flex h-screen w-full bg-[#09090b] text-foreground font-sans antialiased overflow-hidden">
        {/* Collapsible Left Navigation Sidebar */}
        <Sidebar
          currentRoute={currentRoute}
          onNavigate={(route) => {
            setSelectedFolder(null);
            setCurrentRoute(route);
          }}
          selectedProjectFolder={selectedFolder}
          onDeselectProject={() => setSelectedFolder(null)}
          isConnected={isConnected}
          autoShutdown={autoShutdown}
          isTestingConnection={isTestingConnection}
          onTestConnection={handleTestConnection}
          onToggleAutoShutdown={handleToggleAutoShutdown}
        />

        {/* Main Content Area (SidebarInset) */}
        <SidebarInset className="flex-1 flex flex-col h-screen overflow-hidden bg-[#09090b]">
          {/* Top Header Controls Bar */}
          <TopBar
            isConnected={isConnected}
            autoShutdown={autoShutdown}
            isTestingConnection={isTestingConnection}
            onTestConnection={handleTestConnection}
            onToggleAutoShutdown={handleToggleAutoShutdown}
            onOpenSocialModal={() => {
              setSelectedFolder(null);
              setCurrentRoute("social_providers");
            }}
            onOpenSettingsModal={() => setIsSystemModalOpen(true)}
          />

          {/* Dynamic Full-Width Main Body Container */}
          <main className="flex-1 p-6 md:p-8 overflow-y-auto w-full space-y-6">
            <ErrorBoundary>
              {selectedFolder ? (
                <ProjectDetails
                  folder={selectedFolder}
                  onBack={() => setSelectedFolder(null)}
                  onRunSuccess={() => {
                    setSelectedFolder(null);
                    setCurrentRoute("queue");
                  }}
                />
              ) : (
                <>
                  {currentRoute === "projects" && (
                    <ProjectGrid onSelectProject={handleSelectProject} />
                  )}

                  {currentRoute === "novels" && <NovelsPage />}

                  {currentRoute === "cloud_data" && <CloudDataPage />}

                  {currentRoute === "queue" && <QueueAndLogs />}

                  {(currentRoute === "social_providers" || currentRoute === "ai_providers") && (
                    <SocialProvidersPage />
                  )}

                  {currentRoute === "system_settings" && (
                    <SystemSettingsModal isOpen={true} onClose={() => setCurrentRoute("projects")} />
                  )}
                </>
              )}
            </ErrorBoundary>
          </main>
        </SidebarInset>

        {/* Modals */}
        {isSystemModalOpen && (
          <SystemSettingsModal isOpen={true} onClose={() => setIsSystemModalOpen(false)} />
        )}

        <Toaster />
      </div>
    </SidebarProvider>
  );
}

export default App;
