import React, { useState, useEffect } from "react";
import { toast } from "sonner";
import {
  Share2,
  Calendar,
  Clock,
  Send,
  Plus,
  Trash2,
  Video,
  Sparkles,
  RefreshCw,
  ExternalLink,
  Shield,
  Layers,
  Flame,
  Check,
  Globe,
  SlidersHorizontal,
  ThumbsUp,
  MessageCircle,
  Share,
  Music2,
  Key,
} from "lucide-react";
import {
  fetchSocialSettings,
  saveSocialSettings,
  publishSocialVideo,
  scheduleSocialVideo,
  fetchScheduledPosts,
  deleteScheduledPost,
  fetchSocialJobs,
  selectNativeFiles,
} from "../lib/api";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Badge } from "./ui/badge";
import { Input } from "./ui/input";
import { Textarea } from "./ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "./ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "./ui/dialog";

interface AccountItem {
  id: string;
  account_name: string;
  enabled: boolean;
  is_default?: boolean;
  avatar?: string;
  [key: string]: any;
}

interface PlatformDef {
  key: string;
  name: string;
  iconBg: string;
  icon: string;
  badgeColor: string;
  fields: { key: string; label: string; placeholder?: string }[];
}

const POSTIZ_PLATFORMS: PlatformDef[] = [
  {
    key: "youtube",
    name: "YouTube",
    iconBg: "bg-red-600",
    icon: "▶",
    badgeColor: "bg-red-500",
    fields: [
      { key: "access_token", label: "Access Token", placeholder: "ya29.xxxxxxxx..." },
      { key: "refresh_token", label: "Refresh Token", placeholder: "1//04xxxxxxx..." },
      { key: "client_id", label: "Client ID", placeholder: "xxxxxx.apps.googleusercontent.com" },
      { key: "client_secret", label: "Client Secret", placeholder: "GOCSPX-xxxxxxx..." },
    ],
  },
  {
    key: "tiktok",
    name: "TikTok",
    iconBg: "bg-black border border-cyan-500/40",
    icon: "🎵",
    badgeColor: "bg-cyan-500",
    fields: [
      { key: "access_token", label: "Access Token", placeholder: "act.xxxxxxxx..." },
      { key: "refresh_token", label: "Refresh Token", placeholder: "rft.xxxxxxxx..." },
      { key: "client_key", label: "Client Key", placeholder: "awxxxxxxxx..." },
      { key: "client_secret", label: "Client Secret", placeholder: "xxxxxxxx..." },
    ],
  },
  {
    key: "facebook",
    name: "Facebook",
    iconBg: "bg-blue-600",
    icon: "🔵",
    badgeColor: "bg-blue-600",
    fields: [
      { key: "access_token", label: "Page Access Token", placeholder: "EAAGxxxxxxx..." },
      { key: "page_id", label: "Facebook Page ID", placeholder: "1000xxxxxxxxx" },
    ],
  },
  {
    key: "instagram",
    name: "Instagram",
    iconBg: "bg-gradient-to-tr from-amber-500 via-pink-500 to-purple-600",
    icon: "📸",
    badgeColor: "bg-pink-500",
    fields: [
      { key: "access_token", label: "User Access Token", placeholder: "IGQVJxxxxxxx..." },
      { key: "instagram_account_id", label: "Instagram Account ID", placeholder: "1784xxxxxxxxx" },
    ],
  },
  {
    key: "threads",
    name: "Threads",
    iconBg: "bg-zinc-800",
    icon: "💬",
    badgeColor: "bg-zinc-600",
    fields: [
      { key: "access_token", label: "Threads Token", placeholder: "THQVJxxxxxxx..." },
      { key: "user_id", label: "User ID", placeholder: "256xxxxxxxxx" },
    ],
  },
  {
    key: "linkedin",
    name: "LinkedIn",
    iconBg: "bg-sky-700",
    icon: "💼",
    badgeColor: "bg-sky-600",
    fields: [
      { key: "access_token", label: "Access Token", placeholder: "AQVxxxxxxx..." },
      { key: "author_urn", label: "Author URN", placeholder: "urn:li:person:xxxxxx" },
    ],
  },
];

export const SocialProvidersPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<string>("channels");

  // Publishing Composer State
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>(["youtube"]);
  const [videoFilePath, setVideoFilePath] = useState<string>("");
  const [videoUrl, setVideoUrl] = useState<string>("");
  const [postTitle, setPostTitle] = useState<string>("");
  const [postDescription, setPostDescription] = useState<string>("");
  const [postTags, setPostTags] = useState<string>("shorts, trending, capcut");
  const [scheduledDateTime, setScheduledDateTime] = useState<string>("");
  const [isPublishing, setIsPublishing] = useState<boolean>(false);

  // Schedules & History State
  const [scheduledPosts, setScheduledPosts] = useState<any[]>([]);
  const [recentJobs, setRecentJobs] = useState<any[]>([]);
  const [isLoadingSchedules, setIsLoadingSchedules] = useState<boolean>(false);

  // Settings & Accounts State
  const [settings, setSettings] = useState<any>({});
  const [addChannelModalOpen, setAddChannelModalOpen] = useState<boolean>(false);
  const [selectedProviderKey, setSelectedProviderKey] = useState<string | null>(null);
  const [accountModalOpen, setAccountModalOpen] = useState<boolean>(false);
  const [editingAccount, setEditingAccount] = useState<AccountItem | null>(null);

  useEffect(() => {
    loadSettings();
    loadSchedulesAndJobs();
    const interval = setInterval(loadSchedulesAndJobs, 8000);

    // Listen for OAuth Success postMessage from popup window
    const handleOAuthMessage = (event: MessageEvent) => {
      if (event.data && event.data.type === "OAUTH_YOUTUBE_SUCCESS") {
        toast.success("🎉 Đã kết nối kênh YouTube thành công!");
        loadSettings();
      }
    };
    window.addEventListener("message", handleOAuthMessage);

    return () => {
      clearInterval(interval);
      window.removeEventListener("message", handleOAuthMessage);
    };
  }, []);

  const loadSettings = async () => {
    try {
      const data = await fetchSocialSettings();
      setSettings(data || {});
    } catch (e) {
      console.warn("Could not load settings:", e);
    }
  };

  const loadSchedulesAndJobs = async () => {
    setIsLoadingSchedules(true);
    try {
      const [schedules, jobs] = await Promise.all([
        fetchScheduledPosts(),
        fetchSocialJobs(),
      ]);
      setScheduledPosts(schedules || []);
      setRecentJobs(jobs || []);
    } catch (e) {
      console.warn("Could not load schedules:", e);
    } finally {
      setIsLoadingSchedules(false);
    }
  };

  const togglePlatform = (key: string) => {
    setSelectedPlatforms((prev) =>
      prev.includes(key) ? prev.filter((p) => p !== key) : [...prev, key]
    );
  };

  const applyBestTime = (timeStr: string) => {
    const today = new Date();
    const [hours, minutes] = timeStr.split(":").map(Number);
    today.setHours(hours, minutes, 0, 0);
    if (today.getTime() < Date.now()) {
      today.setDate(today.getDate() + 1);
    }
    const isoString = new Date(today.getTime() - today.getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 16);
    setScheduledDateTime(isoString);
    toast.success(`Đã chọn khung giờ vàng: ${timeStr}`, {
      description: `Lên lịch đăng vào: ${isoString.replace("T", " ")}`,
    });
  };

  const handleSelectVideoFile = async () => {
    try {
      const files = await selectNativeFiles();
      if (files && files.length > 0) {
        setVideoFilePath(files[0]);
        if (!postTitle) {
          const fileName = files[0].split(/[/\\]/).pop() || "";
          setPostTitle(fileName.replace(/\.[^/.]+$/, ""));
        }
        toast.success("Đã chọn video!", { description: files[0] });
      }
    } catch (err: any) {
      toast.error("Lỗi chọn file", { description: err.message });
    }
  };

  const handlePublishNow = async () => {
    if (!videoFilePath && !videoUrl) {
      toast.error("Vui lòng chọn file video hoặc nhập link Video URL!");
      return;
    }
    if (selectedPlatforms.length === 0) {
      toast.error("Vui lòng chọn ít nhất 1 mạng xã hội!");
      return;
    }

    setIsPublishing(true);
    try {
      const tagsArray = postTags
        .split(/[,#]/)
        .map((t) => t.trim())
        .filter(Boolean);

      const payload = {
        file_path: videoFilePath || undefined,
        video_url: videoUrl || undefined,
        title: postTitle || "Video Mới",
        description: postDescription,
        platforms: selectedPlatforms,
        privacy_status: "public" as const,
        tags: tagsArray,
      };

      const res = await publishSocialVideo(payload);
      if (res.success || res.ok) {
        toast.success("🚀 Đã xuất bản video thành công!");
        loadSchedulesAndJobs();
        setActiveTab("history");
      } else {
        toast.error("Lỗi xuất bản", { description: res.error || res.message });
      }
    } catch (err: any) {
      toast.error("Lỗi gọi API", {
        description: err.response?.data?.error || err.message || String(err),
      });
    } finally {
      setIsPublishing(false);
    }
  };

  const handleSchedulePost = async () => {
    if (!videoFilePath && !videoUrl) {
      toast.error("Vui lòng chọn file video hoặc nhập link Video URL!");
      return;
    }
    if (!scheduledDateTime) {
      toast.error("Vui lòng chọn thời gian hoặc bấm Khung Giờ Vàng!");
      return;
    }

    setIsPublishing(true);
    try {
      const tagsArray = postTags
        .split(/[,#]/)
        .map((t) => t.trim())
        .filter(Boolean);

      const payload = {
        file_path: videoFilePath || undefined,
        video_url: videoUrl || undefined,
        title: postTitle || "Video Mới #Shorts",
        description: postDescription,
        platforms: selectedPlatforms,
        privacy_status: "public" as const,
        tags: tagsArray,
        scheduled_at: scheduledDateTime,
      };

      const res = await scheduleSocialVideo(payload);
      if (res.success || res.ok) {
        toast.success("⏰ Đã lên lịch đăng bài thành công!");
        loadSchedulesAndJobs();
        setActiveTab("history");
      } else {
        toast.error("Lỗi lên lịch", { description: res.error || res.message });
      }
    } catch (err: any) {
      toast.error("Lỗi gọi API", {
        description: err.response?.data?.error || err.message || String(err),
      });
    } finally {
      setIsPublishing(false);
    }
  };

  const handleDeleteSchedule = async (scheduleId: string) => {
    try {
      await deleteScheduledPost(scheduleId);
      toast.success("Đã hủy lịch đăng!");
      loadSchedulesAndJobs();
    } catch (err: any) {
      toast.error("Lỗi hủy lịch", { description: err.message });
    }
  };

  // Google OAuth Popup using exact Postiz Redirect URI (Port 4200)
  const handleConnectYouTubeOAuth = () => {
    const oauthUrl = `http://127.0.0.1:9001/api/v1/auth/youtube/login?redirect_uri=${encodeURIComponent(
      "http://localhost:4200/integrations/social/youtube"
    )}`;
    window.open(oauthUrl, "GoogleOAuth", "width=600,height=700");
  };

  const handleSaveAccount = async () => {
    if (!selectedProviderKey || !editingAccount) return;
    const currentAccounts = settings[selectedProviderKey] || [];
    let updatedAccounts: AccountItem[];

    const exists = currentAccounts.some((a: AccountItem) => a.id === editingAccount.id);
    if (exists) {
      updatedAccounts = currentAccounts.map((a: AccountItem) =>
        a.id === editingAccount.id ? editingAccount : a
      );
    } else {
      updatedAccounts = [...currentAccounts, editingAccount];
    }

    const newSettings = { ...settings, [selectedProviderKey]: updatedAccounts };
    try {
      await saveSocialSettings(newSettings);
      setSettings(newSettings);
      setAccountModalOpen(false);
      toast.success("Đã lưu cấu hình kênh!");
    } catch (e: any) {
      toast.error("Lỗi lưu", { description: e.message });
    }
  };

  const handleDeleteAccount = async (providerKey: string, accountId: string) => {
    const currentAccounts = settings[providerKey] || [];
    const updated = currentAccounts.filter((a: AccountItem) => a.id !== accountId);
    const newSettings = { ...settings, [providerKey]: updated };
    try {
      await saveSocialSettings(newSettings);
      setSettings(newSettings);
      toast.success("Đã xóa kênh!");
    } catch (e: any) {
      toast.error("Lỗi xóa", { description: e.message });
    }
  };

  const getConnectedAccounts = (platformKey: string): AccountItem[] => {
    // 1. Direct array under settings[platformKey]
    if (Array.isArray(settings[platformKey]) && settings[platformKey].length > 0) {
      return settings[platformKey];
    }
    // 2. Direct object under settings[platformKey]
    const directObj = settings[platformKey];
    if (
      directObj &&
      typeof directObj === "object" &&
      (directObj.enabled || directObj.refresh_token || directObj.access_token || directObj.client_id)
    ) {
      return [
        {
          id: directObj.id || `${platformKey}_main`,
          account_name:
            directObj.account_name ||
            (platformKey === "youtube"
              ? "Tô Mèo YouTube (@vizitomeo1)"
              : `${platformKey.charAt(0).toUpperCase() + platformKey.slice(1)} Channel`),
          enabled: directObj.enabled !== false,
          ...directObj,
        },
      ];
    }
    // 3. Nested under settings.social_credentials[platformKey]
    const creds = settings.social_credentials?.[platformKey];
    if (
      creds &&
      typeof creds === "object" &&
      (creds.enabled || creds.refresh_token || creds.access_token || creds.client_id)
    ) {
      return [
        {
          id: creds.id || `${platformKey}_main`,
          account_name:
            creds.account_name ||
            (platformKey === "youtube"
              ? "Tô Mèo YouTube (@vizitomeo1)"
              : `${platformKey.charAt(0).toUpperCase() + platformKey.slice(1)} Channel`),
          enabled: creds.enabled !== false,
          ...creds,
        },
      ];
    }
    return [];
  };

  const totalChannelsCount = POSTIZ_PLATFORMS.reduce((sum, plat) => {
    return sum + getConnectedAccounts(plat.key).length;
  }, 0);

  return (
    <div className="w-full space-y-4 animate-in fade-in-50 duration-200">
      {/* Top Header (100% Postiz Style) */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-2 border-b border-zinc-800/80">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
            <Share2 className="w-5 h-5 text-blue-400" />
            Social Channels & Integrations
          </h1>
          <p className="text-xs text-zinc-400">
            Quản lý kênh mạng xã hội, kết nối 1-Click OAuth và xuất bản video tự động theo chuẩn Postiz.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={loadSchedulesAndJobs}
            className="h-8 text-xs border-zinc-800 bg-zinc-900/60 hover:bg-zinc-800 text-zinc-300"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1 ${isLoadingSchedules ? "animate-spin" : ""}`} />
            Làm mới
          </Button>
          <Button
            size="sm"
            onClick={() => setAddChannelModalOpen(true)}
            className="h-8 bg-[#622FF6] hover:bg-[#5222E0] text-white font-semibold text-xs gap-1.5 shadow-sm shadow-[#622FF6]/20"
          >
            <Plus className="w-3.5 h-3.5" /> Thêm Kênh (Add Channel)
          </Button>
        </div>
      </div>

      {/* Main Tabs Navigation (Postiz-Style) */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-3 max-w-md bg-zinc-900/80 border border-zinc-800/80 p-0.5 rounded-lg h-9">
          <TabsTrigger value="channels" className="text-xs font-semibold gap-1.5 data-[state=active]:bg-[#622FF6] data-[state=active]:text-white">
            <Globe className="w-3.5 h-3.5" />
            Kênh Đã Kết Nối
            {totalChannelsCount > 0 && (
              <span className="ml-1 px-1.5 py-0.2 rounded-full text-[10px] bg-white/20 text-white font-bold">
                {totalChannelsCount}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="composer" className="text-xs font-semibold gap-1.5 data-[state=active]:bg-[#622FF6] data-[state=active]:text-white">
            <Send className="w-3.5 h-3.5" />
            Studio Đăng Bài
          </TabsTrigger>
          <TabsTrigger value="history" className="text-xs font-semibold gap-1.5 data-[state=active]:bg-[#622FF6] data-[state=active]:text-white">
            <Calendar className="w-3.5 h-3.5" />
            Lịch Hẹn & Hàng Đợi
            {scheduledPosts.length > 0 && (
              <span className="ml-1 px-1.5 py-0.2 rounded-full text-[10px] bg-amber-500 text-black font-bold">
                {scheduledPosts.length}
              </span>
            )}
          </TabsTrigger>
        </TabsList>

        {/* TAB 1: KÊNH ĐÃ KẾT NỐI (POSTIZ INTEGRATION LIST) */}
        <TabsContent value="channels" className="space-y-4 mt-4">
          <div className="flex items-center justify-between">
            <div className="text-xs font-bold text-zinc-300 uppercase tracking-wider flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5 text-emerald-400" />
              Danh Sách Kênh ({totalChannelsCount})
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setAddChannelModalOpen(true)}
              className="h-7 text-xs border-zinc-800 bg-zinc-900/60 hover:bg-zinc-800 text-zinc-300 gap-1"
            >
              <Plus className="w-3 h-3" /> Kết Nối Kênh Khác
            </Button>
          </div>

          {totalChannelsCount === 0 ? (
            <div className="p-8 rounded-xl border border-dashed border-zinc-800 bg-zinc-950/40 text-center space-y-3">
              <div className="w-12 h-12 rounded-full bg-zinc-900 border border-zinc-800 mx-auto flex items-center justify-center text-zinc-500">
                <Globe className="w-6 h-6" />
              </div>
              <div className="space-y-1">
                <div className="text-sm font-bold text-zinc-200">Chưa có kênh mạng xã hội nào được kết nối</div>
                <div className="text-xs text-zinc-400 max-w-sm mx-auto">
                  Hãy bấm Thêm Kênh để kết nối YouTube, TikTok, Facebook hoặc Instagram và bắt đầu xuất bản tự động.
                </div>
              </div>
              <Button
                size="sm"
                onClick={() => setAddChannelModalOpen(true)}
                className="bg-[#622FF6] hover:bg-[#5222E0] text-white text-xs font-semibold gap-1.5"
              >
                <Plus className="w-3.5 h-3.5" /> Thêm Kênh Ngay
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {POSTIZ_PLATFORMS.map((plat) => {
                const accounts: AccountItem[] = getConnectedAccounts(plat.key);
                if (accounts.length === 0) return null;

                return accounts.map((acc) => (
                  <div
                    key={acc.id}
                    className="p-3.5 rounded-xl bg-zinc-900/60 border border-zinc-800 hover:border-zinc-700 flex items-center justify-between gap-3 shadow-sm transition-all"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      {/* Avatar with bottom-right platform badge */}
                      <div className="relative shrink-0">
                        <div className="w-10 h-10 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center text-xs font-bold text-zinc-200">
                          {acc.account_name.slice(0, 2).toUpperCase()}
                        </div>
                        <div className={`absolute -bottom-1 -right-1 w-4 h-4 rounded-full ${plat.iconBg} flex items-center justify-center text-[9px] text-white border border-zinc-900`}>
                          {plat.icon}
                        </div>
                      </div>
                      <div className="min-w-0">
                        <div className="text-xs font-bold text-zinc-200 truncate">{acc.account_name}</div>
                        <div className="text-[10px] text-emerald-400 font-medium flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                          Đang hoạt động (Active)
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setSelectedProviderKey(plat.key);
                          setEditingAccount(acc);
                          setAccountModalOpen(true);
                        }}
                        className="h-7 w-7 p-0 text-zinc-400 hover:text-zinc-200"
                      >
                        <SlidersHorizontal className="w-3.5 h-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDeleteAccount(plat.key, acc.id)}
                        className="h-7 w-7 p-0 text-red-400 hover:text-red-300 hover:bg-red-950/30"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                ));
              })}
            </div>
          )}
        </TabsContent>

        {/* TAB 2: STUDIO ĐĂNG BÀI (EXACT POSTIZ COMPOSER + PHONE MOCKUP PREVIEW) */}
        <TabsContent value="composer" className="space-y-4 mt-4">
          {/* Postiz-Style Channel Picker Ribbon */}
          <div className="p-3 rounded-xl bg-zinc-900/60 border border-zinc-800 space-y-1.5">
            <div className="text-xs font-bold text-zinc-300 flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-[#622FF6]" />
              Chọn Kênh Xuất Bản Đồng Thời (Bấm để kích hoạt):
            </div>
            <div className="flex flex-wrap items-center gap-2 pt-0.5">
              {POSTIZ_PLATFORMS.map((plat) => {
                const isSelected = selectedPlatforms.includes(plat.key);
                return (
                  <div
                    key={plat.key}
                    onClick={() => togglePlatform(plat.key)}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border cursor-pointer transition-all ${
                      isSelected
                        ? "bg-[#622FF6]/20 border-[#622FF6] text-white font-bold shadow-sm shadow-[#622FF6]/20"
                        : "bg-zinc-950/60 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    <div className={`w-5 h-5 rounded ${plat.iconBg} flex items-center justify-center text-[10px] text-white`}>
                      {plat.icon}
                    </div>
                    <span className="text-xs">{plat.name}</span>
                    {isSelected && <Check className="w-3 h-3 text-[#622FF6]" />}
                  </div>
                );
              })}
            </div>
          </div>

          {/* 2-Column Composer: Left = Form, Right = Mobile Phone Preview (Postiz Style) */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            {/* Left 7 Columns: Video Source & Metadata */}
            <div className="lg:col-span-7 space-y-3">
              <Card className="bg-zinc-900/60 border-zinc-800 p-4 space-y-3">
                <div className="text-xs font-bold text-zinc-200 flex items-center gap-1.5">
                  <Video className="w-3.5 h-3.5 text-purple-400" /> Nguồn Video
                </div>
                <div className="space-y-2">
                  <div className="flex gap-2">
                    <Input
                      value={videoFilePath}
                      onChange={(e) => setVideoFilePath(e.target.value)}
                      placeholder="Chọn file video (.mp4, .mov)..."
                      className="bg-zinc-950 border-zinc-800 text-xs h-8"
                    />
                    <Button
                      type="button"
                      size="sm"
                      onClick={handleSelectVideoFile}
                      className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs h-8 shrink-0"
                    >
                      Chọn File
                    </Button>
                  </div>
                  <Input
                    value={videoUrl}
                    onChange={(e) => setVideoUrl(e.target.value)}
                    placeholder="Hoặc nhập link URL (YouTube/TikTok/Douyin)..."
                    className="bg-zinc-950 border-zinc-800 text-xs h-8"
                  />
                </div>
              </Card>

              <Card className="bg-zinc-900/60 border-zinc-800 p-4 space-y-3">
                <div className="text-xs font-bold text-zinc-200 flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-yellow-400" /> Tiêu Đề & Nội Dung Bài Viết
                  </span>
                  <span className="text-[10px] text-zinc-500">{postDescription.length} / 5000 ký tự</span>
                </div>
                <div className="space-y-2.5">
                  <Input
                    value={postTitle}
                    onChange={(e) => setPostTitle(e.target.value)}
                    placeholder="Tiêu đề video ấn tượng #Shorts..."
                    className="bg-zinc-950 border-zinc-800 text-xs h-8 font-medium"
                  />
                  <Textarea
                    value={postDescription}
                    onChange={(e) => setPostDescription(e.target.value)}
                    placeholder="Mô tả bài đăng, kêu gọi đăng ký kênh, liên hệ..."
                    rows={3}
                    className="bg-zinc-950 border-zinc-800 text-xs resize-none"
                  />
                  <Input
                    value={postTags}
                    onChange={(e) => setPostTags(e.target.value)}
                    placeholder="shorts, trending, capcut, viral"
                    className="bg-zinc-950 border-zinc-800 text-xs h-8"
                  />
                </div>
              </Card>

              <Card className="bg-zinc-900/60 border-zinc-800 p-4 space-y-2.5">
                <div className="text-xs font-bold text-zinc-200 flex items-center gap-1.5">
                  <Flame className="w-3.5 h-3.5 text-orange-400" /> Khung Giờ Vàng (Smart Scheduling)
                </div>
                <div className="grid grid-cols-3 gap-1.5">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => applyBestTime("11:30")}
                    className="border-zinc-800 bg-zinc-950 hover:bg-zinc-800 h-8 text-[11px] p-0 text-amber-400"
                  >
                    ⚡ 11:30 Trưa
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => applyBestTime("19:00")}
                    className="border-zinc-800 bg-zinc-950 hover:bg-zinc-800 h-8 text-[11px] p-0 text-orange-400"
                  >
                    🔥 19:00 Tối
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => applyBestTime("20:30")}
                    className="border-zinc-800 bg-zinc-950 hover:bg-zinc-800 h-8 text-[11px] p-0 text-emerald-400"
                  >
                    ⭐ 20:30 Đêm
                  </Button>
                </div>
                <Input
                  type="datetime-local"
                  value={scheduledDateTime}
                  onChange={(e) => setScheduledDateTime(e.target.value)}
                  className="bg-zinc-950 border-zinc-800 text-xs h-8 mt-1"
                />
              </Card>

              <div className="grid grid-cols-2 gap-2 pt-1">
                <Button
                  type="button"
                  onClick={handlePublishNow}
                  disabled={isPublishing}
                  className="bg-[#622FF6] hover:bg-[#5222E0] text-white font-bold h-10 text-xs gap-1.5 shadow-md shadow-[#622FF6]/20"
                >
                  <Send className={`w-3.5 h-3.5 ${isPublishing ? "animate-spin" : ""}`} />
                  🚀 Đăng Ngay
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleSchedulePost}
                  disabled={isPublishing}
                  className="border-zinc-800 bg-zinc-900/80 hover:bg-zinc-800 text-zinc-200 font-semibold h-10 text-xs gap-1.5"
                >
                  <Calendar className="w-3.5 h-3.5 text-amber-400" />
                  ⏰ Lên Lịch Đăng
                </Button>
              </div>
            </div>

            {/* Right 5 Columns: Postiz Mobile Phone Screen Mockup */}
            <div className="lg:col-span-5 flex flex-col items-center justify-start">
              <div className="w-full max-w-[280px] rounded-[36px] bg-black border-[4px] border-zinc-700/80 shadow-2xl p-2.5 relative overflow-hidden flex flex-col justify-between aspect-[9/16]">
                {/* Notch */}
                <div className="w-20 h-4 bg-zinc-800 rounded-full mx-auto mb-2 shrink-0" />

                {/* Video Mockup Area */}
                <div className="flex-1 rounded-[24px] bg-zinc-900/90 relative overflow-hidden flex flex-col justify-between p-3 border border-zinc-800/80">
                  {/* Top Bar inside Phone */}
                  <div className="flex items-center justify-between text-[10px] text-zinc-400">
                    <span className="font-bold text-white flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full bg-red-500"></span> Shorts
                    </span>
                    <span>HD 1080p</span>
                  </div>

                  {/* Center Play Indicator */}
                  <div className="flex items-center justify-center my-auto">
                    <div className="w-12 h-12 rounded-full bg-white/10 backdrop-blur-md flex items-center justify-center text-white text-lg">
                      ▶
                    </div>
                  </div>

                  {/* Right Social Actions Overlay */}
                  <div className="absolute right-2 bottom-16 flex flex-col items-center gap-3 text-white">
                    <div className="flex flex-col items-center text-[10px]">
                      <div className="w-7 h-7 rounded-full bg-zinc-800/80 flex items-center justify-center">
                        <ThumbsUp className="w-3.5 h-3.5" />
                      </div>
                      <span>12.4K</span>
                    </div>
                    <div className="flex flex-col items-center text-[10px]">
                      <div className="w-7 h-7 rounded-full bg-zinc-800/80 flex items-center justify-center">
                        <MessageCircle className="w-3.5 h-3.5" />
                      </div>
                      <span>856</span>
                    </div>
                    <div className="flex flex-col items-center text-[10px]">
                      <div className="w-7 h-7 rounded-full bg-zinc-800/80 flex items-center justify-center">
                        <Share className="w-3.5 h-3.5" />
                      </div>
                      <span>Share</span>
                    </div>
                  </div>

                  {/* Bottom Video Metadata */}
                  <div className="space-y-1 z-10">
                    <div className="flex items-center gap-1.5">
                      <div className="w-5 h-5 rounded-full bg-red-600 flex items-center justify-center text-[8px] font-bold text-white">
                        YT
                      </div>
                      <span className="text-[11px] font-bold text-white truncate max-w-[140px]">
                        @yourchannel
                      </span>
                    </div>
                    <div className="text-[10px] text-zinc-100 font-medium line-clamp-2 leading-tight">
                      {postTitle || "Tiêu đề video Shorts xuất hiện ở đây..."}
                    </div>
                    <div className="text-[9px] text-zinc-400 truncate flex items-center gap-1">
                      <Music2 className="w-2.5 h-2.5" /> Âm thanh gốc - CapCut Studio
                    </div>
                  </div>
                </div>

                {/* Bottom Home Indicator */}
                <div className="w-24 h-1 bg-zinc-600 rounded-full mx-auto mt-2 shrink-0" />
              </div>
            </div>
          </div>
        </TabsContent>

        {/* TAB 3: LỊCH HẸN & HÀNG ĐỢI */}
        <TabsContent value="history" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card className="bg-zinc-900/60 border-zinc-800 p-4 space-y-3">
              <div className="text-xs font-bold text-zinc-200 flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <Calendar className="w-3.5 h-3.5 text-blue-400" /> Video Đã Lên Lịch ({scheduledPosts.length})
                </span>
              </div>
              <div className="space-y-2 max-h-[400px] overflow-y-auto">
                {scheduledPosts.length === 0 ? (
                  <div className="text-center py-8 text-zinc-500 text-xs">
                    Chưa có lịch hẹn nào. Hãy lên lịch trong tab Studio Đăng Bài!
                  </div>
                ) : (
                  scheduledPosts.map((item) => (
                    <div
                      key={item.schedule_id}
                      className="p-2.5 rounded-lg bg-zinc-950/70 border border-zinc-800 flex items-center justify-between gap-2"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="font-bold text-xs text-zinc-200 truncate">{item.title}</div>
                        <div className="text-[10px] text-zinc-400 flex items-center gap-1">
                          <Clock className="w-3 h-3 text-amber-400" />
                          <span>{item.scheduled_at?.replace("T", " ")}</span>
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDeleteSchedule(item.schedule_id)}
                        className="h-7 w-7 p-0 text-red-400 hover:bg-red-950/30 shrink-0"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  ))
                )}
              </div>
            </Card>

            <Card className="bg-zinc-900/60 border-zinc-800 p-4 space-y-3">
              <div className="text-xs font-bold text-zinc-200 flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-purple-400" /> Lịch Sử Xuất Bản ({recentJobs.length})
              </div>
              <div className="space-y-2 max-h-[400px] overflow-y-auto">
                {recentJobs.length === 0 ? (
                  <div className="text-center py-8 text-zinc-500 text-xs">
                    Chưa có lượt xuất bản nào gần đây.
                  </div>
                ) : (
                  recentJobs.map((job) => (
                    <div
                      key={job.job_id}
                      className="p-2.5 rounded-lg bg-zinc-950/70 border border-zinc-800 space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-xs text-zinc-200 truncate">
                          {job.payload?.title || "Video Mới"}
                        </span>
                        <Badge variant="outline" className="text-[10px] py-0">
                          {job.status}
                        </Badge>
                      </div>
                      {job.result?.youtube?.video_url && (
                        <a
                          href={job.result.youtube.video_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs text-blue-400 hover:underline flex items-center gap-1 font-medium"
                        >
                          <ExternalLink className="w-3 h-3" /> Xem trên YouTube
                        </a>
                      )}
                    </div>
                  ))
                )}
              </div>
            </Card>
          </div>
        </TabsContent>
      </Tabs>

      {/* Postiz-Style "Add Channel" Modal */}
      <Dialog open={addChannelModalOpen} onOpenChange={setAddChannelModalOpen}>
        <DialogContent className="bg-zinc-900 border-zinc-800 text-zinc-100 max-w-md p-5">
          <DialogHeader>
            <DialogTitle className="text-sm font-bold text-zinc-100 flex items-center gap-2">
              <Plus className="w-4 h-4 text-[#622FF6]" />
              Thêm Kênh Mới (Add Channel)
            </DialogTitle>
          </DialogHeader>

          <div className="grid grid-cols-3 gap-2.5 py-3">
            {POSTIZ_PLATFORMS.map((plat) => (
              <div
                key={plat.key}
                onClick={() => {
                  setAddChannelModalOpen(false);
                  if (plat.key === "youtube") {
                    handleConnectYouTubeOAuth();
                  } else {
                    setSelectedProviderKey(plat.key);
                    setEditingAccount({
                      id: `acc_${Date.now()}`,
                      account_name: `${plat.name} Kênh 1`,
                      enabled: true,
                    });
                    setAccountModalOpen(true);
                  }
                }}
                className="p-3 rounded-xl bg-zinc-950/80 hover:bg-zinc-800/80 border border-zinc-800 hover:border-zinc-700 transition-all flex flex-col items-center justify-center gap-2 cursor-pointer group shadow-sm"
              >
                <div className={`w-9 h-9 rounded-xl ${plat.iconBg} flex items-center justify-center text-white text-base group-hover:scale-110 transition-transform`}>
                  {plat.icon}
                </div>
                <span className="text-xs font-bold text-zinc-200 group-hover:text-[#622FF6] transition-colors">
                  {plat.name}
                </span>
              </div>
            ))}
          </div>

          <DialogFooter className="pt-2 border-t border-zinc-800 flex items-center justify-between">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setAddChannelModalOpen(false);
                setSelectedProviderKey("youtube");
                const currentYt = settings?.youtube?.[0] || {
                  id: "youtube_manual",
                  account_name: "YouTube Channel",
                  client_id: "",
                  client_secret: "",
                  refresh_token: "",
                  enabled: true,
                };
                setEditingAccount(currentYt);
                setAccountModalOpen(true);
              }}
              className="text-xs border-zinc-800 bg-zinc-950 text-zinc-400 gap-1.5"
            >
              <Key className="w-3.5 h-3.5" /> Nhập Token Thủ Công
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setAddChannelModalOpen(false)}
              className="text-xs border-zinc-800 bg-zinc-950 text-zinc-400"
            >
              Đóng
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Account Config Modal */}
      <Dialog open={accountModalOpen} onOpenChange={setAccountModalOpen}>
        <DialogContent className="bg-zinc-900 border-zinc-800 text-zinc-100 max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-xs font-bold text-zinc-100 flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5 text-[#622FF6]" />
              Cấu Hình Kênh:{" "}
              {selectedProviderKey &&
                POSTIZ_PLATFORMS.find((p) => p.key === selectedProviderKey)?.name}
            </DialogTitle>
          </DialogHeader>

          {editingAccount && selectedProviderKey && (
            <div className="space-y-2.5 py-1">
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-zinc-300">Tên Kênh:</label>
                <Input
                  value={editingAccount.account_name}
                  onChange={(e) =>
                    setEditingAccount({ ...editingAccount, account_name: e.target.value })
                  }
                  className="bg-zinc-950 border-zinc-800 text-xs h-8 text-zinc-100"
                />
              </div>

              {(
                POSTIZ_PLATFORMS.find((p) => p.key === selectedProviderKey)?.fields || []
              ).map((field) => (
                <div key={field.key} className="space-y-1">
                  <label className="text-[11px] font-semibold text-zinc-300">{field.label}:</label>
                  <Input
                    type={field.key.includes("secret") || field.key.includes("key") ? "password" : "text"}
                    value={editingAccount[field.key] || ""}
                    onChange={(e) =>
                      setEditingAccount({ ...editingAccount, [field.key]: e.target.value })
                    }
                    placeholder={field.placeholder}
                    className="bg-zinc-950 border-zinc-800 text-xs h-8 text-zinc-100"
                  />
                </div>
              ))}
            </div>
          )}

          <DialogFooter className="pt-2 border-t border-zinc-800">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setAccountModalOpen(false)}
              className="border-zinc-800 bg-zinc-950 text-zinc-400 text-xs h-8"
            >
              Hủy
            </Button>
            <Button
              size="sm"
              onClick={handleSaveAccount}
              className="bg-[#622FF6] hover:bg-[#5222E0] text-white font-semibold text-xs h-8"
            >
              Lưu Kênh
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
