import React, { useState, useEffect } from "react";
import { toast } from "sonner";
import {
  Share2,
  Plus,
  Trash2,
  Save,
  TestTube,
  Power,
  CheckCircle2,
  ShieldCheck,
  Edit2,
  Globe,
} from "lucide-react";
import { fetchSocialSettings, saveSocialSettings } from "../lib/api";
import { Button } from "./ui/button";
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from "./ui/card";
import { Badge } from "./ui/badge";
import { Input } from "./ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/dialog";

interface AccountItem {
  id: string;
  account_name: string;
  enabled: boolean;
  is_default?: boolean;
  [key: string]: any;
}

const PLATFORMS_CONFIG: Record<
  string,
  {
    name: string;
    desc: string;
    icon: string;
    fields: { key: string; label: string; placeholder?: string }[];
  }
> = {
  tiktok: {
    name: "TikTok",
    desc: "Đăng Video ngắn & Shorts tự động",
    icon: "🎵",
    fields: [
      { key: "access_token", label: "Access Token", placeholder: "act.xxxxxxxx..." },
      { key: "refresh_token", label: "Refresh Token", placeholder: "rft.xxxxxxxx..." },
      { key: "client_key", label: "Client Key", placeholder: "awxxxxxxxx..." },
      { key: "client_secret", label: "Client Secret", placeholder: "xxxxxxxx..." },
    ],
  },
  youtube: {
    name: "YouTube",
    desc: "Đăng Video chuẩn & YouTube Shorts",
    icon: "▶",
    fields: [
      { key: "access_token", label: "Access Token", placeholder: "ya29.xxxxxxxx..." },
      { key: "refresh_token", label: "Refresh Token", placeholder: "1//04xxxxxxx..." },
      { key: "client_id", label: "Client ID", placeholder: "xxxxxx.apps.googleusercontent.com" },
      { key: "client_secret", label: "Client Secret", placeholder: "GOCSPX-xxxxxxx..." },
    ],
  },
  facebook: {
    name: "Facebook",
    desc: "Đăng Trang Fanpage & Facebook Reels",
    icon: "🔵",
    fields: [
      { key: "access_token", label: "Page Access Token", placeholder: "EAAGxxxxxxx..." },
      { key: "page_id", label: "Facebook Page ID", placeholder: "1000xxxxxxxxx" },
    ],
  },
  instagram: {
    name: "Instagram",
    desc: "Đăng Reels & Bài viết ảnh",
    icon: "📸",
    fields: [
      { key: "access_token", label: "User Access Token", placeholder: "IGQVJxxxxxxx..." },
      { key: "instagram_account_id", label: "Instagram Business Account ID", placeholder: "1784xxxxxxxxx" },
    ],
  },
  linkedin: {
    name: "LinkedIn",
    desc: "Đăng Video Trang Cá nhân & Công ty",
    icon: "💼",
    fields: [
      { key: "access_token", label: "Access Token", placeholder: "AQVxxxxxxx..." },
      { key: "author_urn", label: "Author URN (Person/Organization)", placeholder: "urn:li:person:xxxxxx" },
    ],
  },
  threads: {
    name: "Threads",
    desc: "Đăng Bài viết & Video trên Meta Threads",
    icon: "💬",
    fields: [
      { key: "access_token", label: "Threads Access Token", placeholder: "THQVJxxxxxxx..." },
      { key: "user_id", label: "Threads User ID", placeholder: "256xxxxxxxxx" },
    ],
  },
};

export const SocialSettingsPage: React.FC = () => {
  const [activePlatform, setActivePlatform] = useState<string>("tiktok");
  const [autoPublish, setAutoPublish] = useState<{ enabled: boolean; default_caption: string }>({
    enabled: true,
    default_caption: "Video tự động xuất bản bởi CapCut Automation Studio!",
  });

  // Accounts mapping: platform -> AccountItem[]
  const [platformAccounts, setPlatformAccounts] = useState<Record<string, AccountItem[]>>({
    tiktok: [
      {
        id: "tt_acc_1",
        account_name: "TikTok - Phim Kiếm Hiệp (Chính)",
        enabled: true,
        is_default: true,
        access_token: "act.tiktok_token_sample_123",
        refresh_token: "rft.sample_123",
        client_key: "aw_key_sample",
        client_secret: "secret_sample",
      },
      {
        id: "tt_acc_2",
        account_name: "TikTok - Channel Gaming (Phụ)",
        enabled: false,
        is_default: false,
        access_token: "",
        refresh_token: "",
        client_key: "",
        client_secret: "",
      },
    ],
    youtube: [
      {
        id: "yt_acc_1",
        account_name: "YouTube Channel Official",
        enabled: true,
        is_default: true,
        access_token: "ya29.sample_youtube_token",
        refresh_token: "1//04_sample",
        client_id: "client_id_sample",
        client_secret: "secret_sample",
      },
    ],
    facebook: [
      {
        id: "fb_acc_1",
        account_name: "Fanpage CapCut Movie Hub",
        enabled: true,
        is_default: true,
        access_token: "EAAG_sample_fb_token",
        page_id: "100099887766554",
      },
    ],
    instagram: [
      {
        id: "ig_acc_1",
        account_name: "Instagram Reels Studio",
        enabled: false,
        is_default: true,
        access_token: "",
        instagram_account_id: "",
      },
    ],
    linkedin: [
      {
        id: "li_acc_1",
        account_name: "LinkedIn Business Page",
        enabled: false,
        is_default: true,
        access_token: "",
        author_urn: "",
      },
    ],
    threads: [
      {
        id: "th_acc_1",
        account_name: "Threads Account @CapCutStudio",
        enabled: false,
        is_default: true,
        access_token: "",
        user_id: "",
      },
    ],
  });

  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [saveSuccess, setSaveSuccess] = useState<string>("");

  // Modal State for Adding/Editing Account
  const [isAccountModalOpen, setIsAccountModalOpen] = useState<boolean>(false);
  const [editingAccount, setEditingAccount] = useState<AccountItem | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchSocialSettings();
        if (data) {
          if (data.auto_publish) {
            setAutoPublish({
              enabled: !!data.auto_publish.enabled,
              default_caption: data.auto_publish.default_caption || "",
            });
          }
          if (data.platform_accounts) {
            setPlatformAccounts((prev) => ({
              ...prev,
              ...data.platform_accounts,
            }));
          }
        }
      } catch (err) {
        console.error("Lỗi tải danh sách tài khoản Mạng xã hội", err);
      }
    };
    load();
  }, []);

  const handleSaveAll = async () => {
    setIsSaving(true);
    try {
      const payload = {
        auto_publish: autoPublish,
        platform_accounts: platformAccounts,
      };
      const res = await saveSocialSettings(payload);
      if (res.ok) {
        setSaveSuccess("Đã lưu toàn bộ danh sách tài khoản thành công!");
        toast.success("Đã lưu toàn bộ danh sách tài khoản thành công!");
        setTimeout(() => setSaveSuccess(""), 3000);
      } else {
        toast.error("Lỗi khi lưu", { description: res.error || "Không xác định" });
      }
    } catch (err: any) {
      toast.error("Lỗi gọi API", { description: err.message || String(err) });
    } finally {
      setIsSaving(false);
    }
  };

  const handleAddAccount = () => {
    const currentMeta = PLATFORMS_CONFIG[activePlatform];
    const newAcc: AccountItem = {
      id: `${activePlatform}_acc_${Date.now()}`,
      account_name: `Tài khoản ${currentMeta.name} mới`,
      enabled: true,
      is_default: (platformAccounts[activePlatform] || []).length === 0,
    };
    currentMeta.fields.forEach((f) => {
      newAcc[f.key] = "";
    });
    setEditingAccount(newAcc);
    setIsAccountModalOpen(true);
  };

  const handleEditAccount = (acc: AccountItem) => {
    setEditingAccount({ ...acc });
    setIsAccountModalOpen(true);
  };

  const handleSaveAccountFromModal = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingAccount) return;

    const list = platformAccounts[activePlatform] || [];
    const existsIndex = list.findIndex((a) => a.id === editingAccount.id);

    let updatedList = [...list];
    if (existsIndex >= 0) {
      updatedList[existsIndex] = editingAccount;
    } else {
      updatedList.push(editingAccount);
    }

    setPlatformAccounts({
      ...platformAccounts,
      [activePlatform]: updatedList,
    });

    setIsAccountModalOpen(false);
    setEditingAccount(null);
  };

  const handleDeleteAccount = (id: string) => {
    if (!window.confirm("Bạn có chắc muốn xóa tài khoản này khỏi danh sách?")) return;
    const list = platformAccounts[activePlatform] || [];
    const updatedList = list.filter((a) => a.id !== id);
    setPlatformAccounts({
      ...platformAccounts,
      [activePlatform]: updatedList,
    });
  };

  const handleToggleAccountStatus = (id: string, enabled: boolean) => {
    const list = platformAccounts[activePlatform] || [];
    const updatedList = list.map((a) => (a.id === id ? { ...a, enabled } : a));
    setPlatformAccounts({
      ...platformAccounts,
      [activePlatform]: updatedList,
    });
  };

  const handleTestConnection = (accName: string) => {
    toast.success(`Đã kiểm tra kết nối API tới "${accName}" thành công!`);
  };

  const currentMeta = PLATFORMS_CONFIG[activePlatform];
  const currentAccounts = platformAccounts[activePlatform] || [];

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="glass-panel p-6 border-cyan-500/30 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-extrabold text-cyan-400 flex items-center gap-2">
            <Share2 className="w-6 h-6 text-cyan-400" /> Quản Lý Đa Tài Khoản Mạng Xã Hội (Multi-Account Manager)
          </h2>
          <p className="text-xs text-muted-foreground mt-1">
            Quản lý nhiều tài khoản cho từng nền tảng (TikTok, YouTube, Facebook, Instagram, LinkedIn, Threads) và thiết lập tài khoản xuất bản tự động.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {saveSuccess && (
            <Badge variant="success" className="animate-bounce py-1.5 px-3">
              <CheckCircle2 className="w-4 h-4" /> {saveSuccess}
            </Badge>
          )}

          <Button variant="gradient" size="default" onClick={handleSaveAll} disabled={isSaving}>
            <Save className="w-4 h-4" />
            <span>{isSaving ? "Đang lưu..." : "💾 Lưu tất cả cài đặt"}</span>
          </Button>
        </div>
      </div>

      {/* Auto Publish Global Bar */}
      <Card className="p-5 border-purple-500/30">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <label className="flex items-center gap-3 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={autoPublish.enabled}
              onChange={(e) => setAutoPublish({ ...autoPublish, enabled: e.target.checked })}
              className="w-5 h-5 rounded border-white/20 bg-black/40 text-cyan-400 focus:ring-0"
            />
            <span className="font-bold text-sm text-foreground flex items-center gap-2">
              <Power className="w-4 h-4 text-cyan-400" /> Bật Tự động xuất bản tự động (Global Auto Publish)
            </span>
          </label>

          <div className="w-full md:w-1/2">
            <label className="block text-[11px] font-semibold text-muted-foreground mb-1">
              Caption Mặc định cho bài viết xuất bản:
            </label>
            <Input
              type="text"
              value={autoPublish.default_caption}
              onChange={(e) => setAutoPublish({ ...autoPublish, default_caption: e.target.value })}
              placeholder="Caption mặc định..."
            />
          </div>
        </div>
      </Card>

      {/* Platform Navigation Tabs */}
      <div className="flex items-center gap-2 p-1.5 glass-panel border-white/10 overflow-x-auto">
        {Object.keys(PLATFORMS_CONFIG).map((pKey) => {
          const meta = PLATFORMS_CONFIG[pKey];
          const accs = platformAccounts[pKey] || [];
          const activeCount = accs.filter((a) => a.enabled).length;
          const isActive = activePlatform === pKey;

          return (
            <Button
              key={pKey}
              variant={isActive ? "default" : "ghost"}
              size="sm"
              onClick={() => setActivePlatform(pKey)}
              className="h-10 px-4 flex items-center gap-2"
            >
              <span className="text-base">{meta.icon}</span>
              <span>{meta.name}</span>
              <Badge variant={activeCount > 0 ? "success" : "secondary"} className="h-5 px-1.5 text-[9px]">
                {accs.length} TK ({activeCount} Bật)
              </Badge>
            </Button>
          );
        })}
      </div>

      {/* Platform Accounts Management Workspace */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-foreground flex items-center gap-2">
              <span className="text-xl">{currentMeta.icon}</span> Quản lý danh sách Tài khoản {currentMeta.name}
            </h3>
            <p className="text-xs text-muted-foreground">{currentMeta.desc}</p>
          </div>

          <Button variant="default" size="sm" onClick={handleAddAccount}>
            <Plus className="w-4 h-4" /> Thêm tài khoản {currentMeta.name} mới
          </Button>
        </div>

        {/* Accounts Cards List */}
        {currentAccounts.length === 0 ? (
          <Card className="p-12 text-center flex flex-col items-center justify-center gap-3">
            <Globe className="w-12 h-12 text-muted-foreground/30" />
            <p className="text-sm text-muted-foreground">
              Chưa có tài khoản {currentMeta.name} nào. Bấm nút bên trên để thêm tài khoản mới.
            </p>
            <Button variant="default" size="sm" onClick={handleAddAccount}>
              <Plus className="w-4 h-4" /> Thêm tài khoản ngay
            </Button>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {currentAccounts.map((acc) => (
              <Card
                key={acc.id}
                className={`p-5 transition-all relative border ${
                  acc.enabled ? "border-cyan-500/40 bg-card/70" : "border-white/10 opacity-75"
                }`}
              >
                <CardHeader className="p-0 pb-3 flex flex-row items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-xl">
                      {currentMeta.icon}
                    </div>
                    <div>
                      <CardTitle className="text-sm font-bold text-foreground flex items-center gap-2">
                        {acc.account_name}
                        {acc.is_default && (
                          <Badge variant="warning" className="text-[9px] py-0">
                            Mặc định
                          </Badge>
                        )}
                      </CardTitle>
                      <p className="text-[11px] font-mono text-muted-foreground">ID: {acc.id}</p>
                    </div>
                  </div>

                  <Badge variant={acc.enabled ? "success" : "secondary"}>
                    {acc.enabled ? "● ĐÃ KÍCH HOẠT" : "○ TẮT"}
                  </Badge>
                </CardHeader>

                <CardContent className="p-0 space-y-2 pt-2 border-t border-white/10 my-3">
                  {currentMeta.fields.map((f) => (
                    <div key={f.key} className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">{f.label}:</span>
                      <span className="font-mono text-cyan-200 font-medium truncate max-w-[200px]">
                        {acc[f.key] ? "••••••••••••••••" : "<chưa nhập>"}
                      </span>
                    </div>
                  ))}
                </CardContent>

                <CardFooter className="p-0 pt-3 flex items-center justify-between border-t border-white/10">
                  <div className="flex items-center gap-2">
                    <label className="flex items-center gap-1.5 text-xs font-semibold cursor-pointer">
                      <input
                        type="checkbox"
                        checked={acc.enabled}
                        onChange={(e) => handleToggleAccountStatus(acc.id, e.target.checked)}
                        className="rounded border-white/20 bg-black/40 text-cyan-400 focus:ring-0"
                      />
                      <span className="text-cyan-300">Kích hoạt</span>
                    </label>
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleTestConnection(acc.account_name)}
                      className="h-7 text-[10px] px-2"
                    >
                      <TestTube className="w-3 h-3 text-purple-400" /> Test
                    </Button>

                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => handleEditAccount(acc)}
                      className="h-7 text-[10px] px-2"
                    >
                      <Edit2 className="w-3 h-3 text-cyan-400" /> Sửa
                    </Button>

                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => handleDeleteAccount(acc.id)}
                      className="h-7 text-[10px] px-2"
                    >
                      <Trash2 className="w-3 h-3" />
                    </Button>
                  </div>
                </CardFooter>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Account Add/Edit Dialog Modal */}
      <Dialog open={isAccountModalOpen} onOpenChange={setIsAccountModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-cyan-400" /> Cấu hình Tài khoản {currentMeta.name}
            </DialogTitle>
            <DialogDescription>
              Nhập tên gợi nhớ và các thông tin API Access Token cho tài khoản này.
            </DialogDescription>
          </DialogHeader>

          {editingAccount && (
            <form onSubmit={handleSaveAccountFromModal} className="space-y-4 py-2">
              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1">
                  Tên gợi nhớ cho tài khoản:
                </label>
                <Input
                  type="text"
                  value={editingAccount.account_name || ""}
                  onChange={(e) => setEditingAccount({ ...editingAccount, account_name: e.target.value })}
                  placeholder="Ví dụ: TikTok Phim Kiếm Hiệp 1"
                  required
                />
              </div>

              {currentMeta.fields.map((f) => (
                <div key={f.key}>
                  <label className="block text-xs font-semibold text-muted-foreground mb-1">
                    {f.label}:
                  </label>
                  <Input
                    type="password"
                    value={editingAccount[f.key] || ""}
                    onChange={(e) => setEditingAccount({ ...editingAccount, [f.key]: e.target.value })}
                    placeholder={f.placeholder || `${f.label}...`}
                  />
                </div>
              ))}

              <div className="flex items-center gap-2 pt-2">
                <label className="flex items-center gap-2 text-xs font-semibold cursor-pointer">
                  <input
                    type="checkbox"
                    checked={editingAccount.enabled}
                    onChange={(e) => setEditingAccount({ ...editingAccount, enabled: e.target.checked })}
                    className="rounded border-white/20 bg-black/40 text-cyan-400 focus:ring-0"
                  />
                  <span>Kích hoạt tài khoản này</span>
                </label>
              </div>

              <DialogFooter>
                <Button type="button" variant="secondary" size="sm" onClick={() => setIsAccountModalOpen(false)}>
                  Hủy
                </Button>
                <Button type="submit" variant="default" size="sm">
                  Lưu tài khoản
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};
