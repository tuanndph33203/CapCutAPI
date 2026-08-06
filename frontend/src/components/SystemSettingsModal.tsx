import React, { useState, useEffect } from "react";
import { toast } from "sonner";
import { Settings, Save, Plus, Trash2, Edit, Bot, Key } from "lucide-react";
import { fetchGlobalSettings, saveGlobalSettings } from "../lib/api";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/dialog";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";

interface SystemSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export interface AiProfile {
  id: string;
  label: string;
  provider: string;
  model: string;
  api_key: string;
  base_url: string;
}

export const SystemSettingsModal: React.FC<SystemSettingsModalProps> = ({ isOpen, onClose }) => {
  const [aiProfiles, setAiProfiles] = useState<AiProfile[]>([]);
  const [defaultTransId, setDefaultTransId] = useState<string>("");
  const [defaultContextId, setDefaultContextId] = useState<string>("");
  const [openreelApiKey, setOpenreelApiKey] = useState<string>("");
  const [openreelRefKeys, setOpenreelRefKeys] = useState<string>("");
  const [isSaving, setIsSaving] = useState<boolean>(false);

  // Profile Editor Modal state
  const [isEditorOpen, setIsEditorOpen] = useState<boolean>(false);
  const [editingIndex, setEditingIndex] = useState<number>(-1);
  const [profileForm, setProfileForm] = useState<AiProfile>({
    id: "",
    label: "",
    provider: "openai",
    model: "gpt-4o-mini",
    api_key: "",
    base_url: "https://api.openai.com/v1",
  });
  const [customProvider, setCustomProvider] = useState<string>("");

  const loadData = async () => {
    try {
      const data = await fetchGlobalSettings();
      const profiles = Array.isArray(data.ai_profiles) ? data.ai_profiles : [];
      setAiProfiles(profiles);
      setDefaultTransId(data.default_translation_ai_profile_id || (profiles[0]?.id || ""));
      setDefaultContextId(data.default_context_ai_profile_id || (profiles[0]?.id || ""));
      setOpenreelApiKey(data.openreel_api_key || "");
      setOpenreelRefKeys(data.openreel_reference_keys || "");
    } catch (err) {
      toast.error("Lỗi tải cấu hình Global Settings");
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen]);

  const handleOpenEditor = (index: number = -1) => {
    setEditingIndex(index);
    if (index >= 0 && aiProfiles[index]) {
      const p = aiProfiles[index];
      setProfileForm({ ...p });
      if (["openai", "gemini", "anthropic"].includes(p.provider)) {
        setCustomProvider("");
      } else {
        setCustomProvider(p.provider);
      }
    } else {
      const newId = `ai-profile-${Date.now().toString().slice(-4)}`;
      setProfileForm({
        id: newId,
        label: `AI Profile ${aiProfiles.length + 1}`,
        provider: "openai",
        model: "gpt-4o-mini",
        api_key: "",
        base_url: "https://api.openai.com/v1",
      });
      setCustomProvider("");
    }
    setIsEditorOpen(true);
  };

  const handleSaveProfileInEditor = (e: React.FormEvent) => {
    e.preventDefault();
    if (!profileForm.label.trim()) {
      toast.error("Vui lòng nhập tên hiển thị (Label)");
      return;
    }

    const finalProvider = profileForm.provider === "custom" ? (customProvider.trim() || "custom") : profileForm.provider;
    const finalProfile: AiProfile = {
      ...profileForm,
      provider: finalProvider,
      id: profileForm.id.trim() || `profile-${Date.now()}`,
    };

    let updated: AiProfile[] = [];
    if (editingIndex >= 0) {
      updated = [...aiProfiles];
      updated[editingIndex] = finalProfile;
    } else {
      updated = [...aiProfiles, finalProfile];
    }

    setAiProfiles(updated);
    if (!defaultTransId) setDefaultTransId(finalProfile.id);
    if (!defaultContextId) setDefaultContextId(finalProfile.id);
    setIsEditorOpen(false);
    toast.success(editingIndex >= 0 ? "Đã cập nhật AI Profile" : "Đã thêm AI Profile mới");
  };

  const handleDeleteProfile = (index: number) => {
    const target = aiProfiles[index];
    if (!target) return;
    const updated = aiProfiles.filter((_, i) => i !== index);
    setAiProfiles(updated);
    if (defaultTransId === target.id) setDefaultTransId(updated[0]?.id || "");
    if (defaultContextId === target.id) setDefaultContextId(updated[0]?.id || "");
    toast.info(`Đã xóa AI Profile: ${target.label}`);
  };

  const handleSaveGlobal = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      const payload = {
        ai_profiles: aiProfiles,
        default_translation_ai_profile_id: defaultTransId || (aiProfiles[0]?.id || ""),
        default_context_ai_profile_id: defaultContextId || (aiProfiles[0]?.id || ""),
        openreel_api_key: openreelApiKey,
        openreel_reference_keys: openreelRefKeys,
      };

      const res = await saveGlobalSettings(payload);
      if (res.ok) {
        toast.success("Đã lưu Global Settings thành công!");
        onClose();
      } else {
        toast.error("Lỗi khi lưu Global Settings", { description: res.error || "Không xác định" });
      }
    } catch (err: any) {
      toast.error("Lỗi gọi API", { description: err.message || String(err) });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <>
      <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-cyan-400 text-lg font-bold">
              <Settings className="w-5 h-5 text-cyan-400" /> Cấu Hình Hệ Thống Chung (Global Settings)
            </DialogTitle>
            <DialogDescription>
              Quản lý các AI Profile Key Engine (ChatGPT, Gemini, Gemma, DeepL) & API Key tích hợp
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSaveGlobal} className="space-y-6 py-2">
            {/* Header section: AI Profiles Table */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-cyan-300 flex items-center gap-1.5">
                  <Bot className="w-4 h-4" /> Danh sách AI Profiles ({aiProfiles.length})
                </h3>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => handleOpenEditor(-1)}
                  className="h-8 text-xs border-cyan-500/40 text-cyan-300 bg-cyan-500/10 hover:bg-cyan-500/20"
                >
                  <Plus className="w-3.5 h-3.5 mr-1" /> + Thêm AI Profile
                </Button>
              </div>

              {aiProfiles.length === 0 ? (
                <div className="p-4 rounded-xl border border-white/10 text-center text-xs text-muted-foreground bg-black/30">
                  Chưa có AI profile nào. Bấm <strong className="text-cyan-400">+ Thêm AI Profile</strong> để tạo mới.
                </div>
              ) : (
                <div className="overflow-x-auto border border-white/10 rounded-xl max-h-60 overflow-y-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead className="bg-black/60 sticky top-0 text-muted-foreground border-b border-white/10">
                      <tr>
                        <th className="p-2.5">Tên hiển thị</th>
                        <th className="p-2.5">Provider</th>
                        <th className="p-2.5">Model</th>
                        <th className="p-2.5">Base URL</th>
                        <th className="p-2.5 text-right">Thao tác</th>
                      </tr>
                    </thead>
                    <tbody>
                      {aiProfiles.map((p, idx) => (
                        <tr key={p.id || idx} className="border-b border-white/5 hover:bg-white/5">
                          <td className="p-2.5 font-bold text-foreground">{p.label || p.id}</td>
                          <td className="p-2.5">
                            <Badge variant="outline" className="text-[10px] uppercase font-mono">
                              {p.provider}
                            </Badge>
                          </td>
                          <td className="p-2.5 font-mono text-cyan-300">{p.model}</td>
                          <td className="p-2.5 font-mono text-muted-foreground truncate max-w-[140px]" title={p.base_url}>
                            {p.base_url || "Standard"}
                          </td>
                          <td className="p-2.5 text-right">
                            <div className="flex items-center justify-end gap-1">
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => handleOpenEditor(idx)}
                                className="h-7 px-2 text-xs"
                              >
                                <Edit className="w-3 h-3 mr-1" /> Sửa
                              </Button>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => handleDeleteProfile(idx)}
                                className="h-7 px-2 text-xs text-red-400 hover:text-red-300"
                              >
                                <Trash2 className="w-3 h-3 mr-1" /> Xóa
                              </Button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Row 2: Default AI Profile Selectors */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 p-4 rounded-xl bg-black/30 border border-white/10">
              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1">
                  AI Profile Dịch phụ đề Mặc định:
                </label>
                <select
                  value={defaultTransId}
                  onChange={(e) => setDefaultTransId(e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-black/50 border border-white/10 rounded-xl text-amber-300 font-semibold"
                >
                  {aiProfiles.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label || p.id} ({p.provider} / {p.model})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1">
                  AI Profile Ngữ cảnh Mặc định:
                </label>
                <select
                  value={defaultContextId}
                  onChange={(e) => setDefaultContextId(e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-black/50 border border-white/10 rounded-xl text-amber-300 font-semibold"
                >
                  {aiProfiles.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label || p.id} ({p.provider} / {p.model})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Row 3: OpenReel Keys */}
            <div className="p-4 rounded-xl bg-black/30 border border-white/10 space-y-3">
              <h4 className="text-xs font-bold text-purple-300 flex items-center gap-1.5">
                <Key className="w-3.5 h-3.5" /> OpenReel Engine Keys
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-medium text-muted-foreground mb-1">OpenReel API Key:</label>
                  <Input
                    type="password"
                    value={openreelApiKey}
                    onChange={(e) => setOpenreelApiKey(e.target.value)}
                    placeholder="sk-openreel-..."
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-muted-foreground mb-1">OpenReel Reference Keys:</label>
                  <Input
                    type="text"
                    value={openreelRefKeys}
                    onChange={(e) => setOpenreelRefKeys(e.target.value)}
                    placeholder="ref-key-1, ref-key-2"
                  />
                </div>
              </div>
            </div>

            <DialogFooter>
              <Button type="button" variant="secondary" size="sm" onClick={onClose}>
                Hủy
              </Button>
              <Button type="submit" variant="default" size="sm" disabled={isSaving}>
                <Save className="w-3.5 h-3.5 mr-1" />
                <span>{isSaving ? "Đang lưu..." : "Lưu Global Settings"}</span>
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Editor Inner Modal */}
      <Dialog open={isEditorOpen} onOpenChange={setIsEditorOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-cyan-400 text-sm font-bold flex items-center gap-1.5">
              <Bot className="w-4 h-4" /> {editingIndex >= 0 ? "Sửa AI Profile" : "Thêm AI Profile Mới"}
            </DialogTitle>
          </DialogHeader>

          <form onSubmit={handleSaveProfileInEditor} className="space-y-3 py-2 text-xs">
            <div>
              <label className="block font-semibold text-muted-foreground mb-1">Tên hiển thị (Label):</label>
              <Input
                type="text"
                value={profileForm.label}
                onChange={(e) => setProfileForm({ ...profileForm, label: e.target.value })}
                placeholder="Ví dụ: GEMMA AI / GPT-4o Key"
                required
              />
            </div>

            <div>
              <label className="block font-semibold text-muted-foreground mb-1">Profile ID:</label>
              <Input
                type="text"
                value={profileForm.id}
                onChange={(e) => setProfileForm({ ...profileForm, id: e.target.value })}
                placeholder="gemma-default"
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block font-semibold text-muted-foreground mb-1">Provider:</label>
                <select
                  value={["openai", "gemini", "anthropic"].includes(profileForm.provider) ? profileForm.provider : "custom"}
                  onChange={(e) => setProfileForm({ ...profileForm, provider: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-black/40 border border-white/10 rounded-xl text-foreground"
                >
                  <option value="openai">OpenAI / Compatible</option>
                  <option value="gemini">Google Gemini</option>
                  <option value="anthropic">Anthropic Claude</option>
                  <option value="custom">Khác (Tự nhập)...</option>
                </select>
              </div>

              <div>
                <label className="block font-semibold text-muted-foreground mb-1">Model Name:</label>
                <Input
                  type="text"
                  value={profileForm.model}
                  onChange={(e) => setProfileForm({ ...profileForm, model: e.target.value })}
                  placeholder="gpt-4o-mini / gemma-4-31b"
                />
              </div>
            </div>

            {profileForm.provider === "custom" && (
              <div>
                <label className="block font-semibold text-muted-foreground mb-1">Provider tùy chỉnh:</label>
                <Input
                  type="text"
                  value={customProvider}
                  onChange={(e) => setCustomProvider(e.target.value)}
                  placeholder="Ví dụ: deepseek / groq"
                />
              </div>
            )}

            <div>
              <label className="block font-semibold text-muted-foreground mb-1">API Key:</label>
              <Input
                type="password"
                value={profileForm.api_key}
                onChange={(e) => setProfileForm({ ...profileForm, api_key: e.target.value })}
                placeholder="sk-..."
              />
            </div>

            <div>
              <label className="block font-semibold text-muted-foreground mb-1">Base URL Endpoint:</label>
              <Input
                type="text"
                value={profileForm.base_url}
                onChange={(e) => setProfileForm({ ...profileForm, base_url: e.target.value })}
                placeholder="https://api.openai.com/v1"
              />
            </div>

            <DialogFooter className="pt-2">
              <Button type="button" variant="secondary" size="sm" onClick={() => setIsEditorOpen(false)}>
                Hủy
              </Button>
              <Button type="submit" variant="default" size="sm">
                Lưu Profile
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
};
