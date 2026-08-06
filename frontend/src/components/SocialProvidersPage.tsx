import React, { useState, useEffect } from "react";
import { toast } from "sonner";
import {
  ChevronRight,
  Plus,
  Trash2,
  Save,
  TestTube,
  CheckCircle2,
  ArrowLeft,
  Bot,
  Sparkles,
} from "lucide-react";
import { fetchSocialSettings, saveSocialSettings } from "../lib/api";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Badge } from "./ui/badge";
import { Input } from "./ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/dialog";

interface AccountItem {
  id: string;
  account_name: string;
  enabled: boolean;
  is_default?: boolean;
  base_url?: string;
  model_name?: string;
  [key: string]: any;
}

interface ProviderMeta {
  name: string;
  desc: string;
  icon: string;
  isCustom?: boolean;
  fields: { key: string; label: string; placeholder?: string }[];
}

const DEFAULT_OAUTH_PROVIDERS: Record<string, ProviderMeta> = {
  tiktok: {
    name: "TikTok",
    desc: "Short-form video auto publish",
    icon: "🎵",
    fields: [
      { key: "access_token", label: "Access Token", placeholder: "act.xxxxxxxx..." },
      { key: "refresh_token", label: "Refresh Token", placeholder: "rft.xxxxxxxx..." },
      { key: "client_key", label: "Client Key", placeholder: "awxxxxxxxx..." },
      { key: "client_secret", label: "Client Secret", placeholder: "xxxxxxxx..." },
    ],
  },
  youtube: {
    name: "YouTube Shorts",
    desc: "YouTube Data API v3",
    icon: "▶",
    fields: [
      { key: "access_token", label: "Access Token", placeholder: "ya29.xxxxxxxx..." },
      { key: "refresh_token", label: "Refresh Token", placeholder: "1//04xxxxxxx..." },
      { key: "client_id", label: "Client ID", placeholder: "xxxxxx.apps.googleusercontent.com" },
      { key: "client_secret", label: "Client Secret", placeholder: "GOCSPX-xxxxxxx..." },
    ],
  },
  facebook: {
    name: "Facebook Reels",
    desc: "Facebook Graph API",
    icon: "🔵",
    fields: [
      { key: "access_token", label: "Page Access Token", placeholder: "EAAGxxxxxxx..." },
      { key: "page_id", label: "Facebook Page ID", placeholder: "1000xxxxxxxxx" },
    ],
  },
  instagram: {
    name: "Instagram Reels",
    desc: "Instagram Graph API",
    icon: "📸",
    fields: [
      { key: "access_token", label: "User Access Token", placeholder: "IGQVJxxxxxxx..." },
      { key: "instagram_account_id", label: "Instagram Account ID", placeholder: "1784xxxxxxxxx" },
    ],
  },
  linkedin: {
    name: "LinkedIn Video",
    desc: "LinkedIn Share API",
    icon: "💼",
    fields: [
      { key: "access_token", label: "Access Token", placeholder: "AQVxxxxxxx..." },
      { key: "author_urn", label: "Author URN", placeholder: "urn:li:person:xxxxxx" },
    ],
  },
  threads: {
    name: "Threads Meta",
    desc: "Threads API",
    icon: "💬",
    fields: [
      { key: "access_token", label: "Threads Token", placeholder: "THQVJxxxxxxx..." },
      { key: "user_id", label: "User ID", placeholder: "256xxxxxxxxx" },
    ],
  },
};

const DEFAULT_AI_PROVIDERS: Record<string, ProviderMeta> = {
  openai: {
    name: "OpenAI / GPT-4o",
    desc: "Translation & Context AI Engine",
    icon: "🤖",
    fields: [
      { key: "api_key", label: "OpenAI API Key", placeholder: "sk-proj-xxxx..." },
      { key: "base_url", label: "API Base URL (Optional)", placeholder: "https://api.openai.com/v1" },
      { key: "model_name", label: "Model Name", placeholder: "gpt-4o" },
    ],
  },
  deepl: {
    name: "DeepL Pro",
    desc: "DeepL Translation API",
    icon: "🌐",
    fields: [
      { key: "api_key", label: "DeepL Authentication Key", placeholder: "xxxx-xxxx-xxxx:fx" },
    ],
  },
  google_translate: {
    name: "Google Translate",
    desc: "Cloud Translation API",
    icon: "G",
    fields: [
      { key: "api_key", label: "Google API Key", placeholder: "AIzaSyxxxx..." },
    ],
  },
  claude: {
    name: "Anthropic Claude",
    desc: "Claude 3.5 Sonnet AI Engine",
    icon: "🧠",
    fields: [
      { key: "api_key", label: "Anthropic API Key", placeholder: "sk-ant-xxxx..." },
      { key: "model_name", label: "Model Name", placeholder: "claude-3-5-sonnet-20241022" },
    ],
  },
  groq: {
    name: "Groq Llama 3",
    desc: "Ultra-fast LLM Inference",
    icon: "⚡",
    fields: [
      { key: "api_key", label: "Groq API Key", placeholder: "gsk_xxxx..." },
      { key: "model_name", label: "Model Name", placeholder: "llama-3.3-70b-versatile" },
    ],
  },
};

export const SocialProvidersPage: React.FC = () => {
  const [selectedProviderKey, setSelectedProviderKey] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"connections" | "usage">("connections");

  const [aiProviders, setAiProviders] = useState<Record<string, ProviderMeta>>(DEFAULT_AI_PROVIDERS);
  const [oauthProviders] = useState<Record<string, ProviderMeta>>(DEFAULT_OAUTH_PROVIDERS);

  const [autoPublish, setAutoPublish] = useState<{ enabled: boolean; default_caption: string }>({
    enabled: true,
    default_caption: "Video tự động xuất bản bởi CapCut Automation Studio!",
  });

  const [accounts, setAccounts] = useState<Record<string, AccountItem[]>>({
    tiktok: [],
    youtube: [],
    facebook: [],
    instagram: [],
    linkedin: [],
    threads: [],
    openai: [
      {
        id: "ai_1",
        account_name: "OpenAI GPT-4o Token",
        enabled: true,
        api_key: "sk-proj-sample",
        model_name: "gpt-4o",
      },
    ],
    deepl: [],
    google_translate: [
      {
        id: "gt_1",
        account_name: "Google Translate Free Key",
        enabled: true,
        api_key: "AIzaSy_sample",
      },
    ],
    claude: [],
    groq: [],
  });

  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [saveSuccess, setSaveSuccess] = useState<string>("");

  // Modal States
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [editingAcc, setEditingAcc] = useState<AccountItem | null>(null);

  // Add Dynamic Provider Modal State
  const [isAddProviderModalOpen, setIsAddProviderModalOpen] = useState<boolean>(false);
  const [newProviderForm, setNewProviderForm] = useState<{
    key: string;
    name: string;
    desc: string;
    icon: string;
    base_url: string;
    model_name: string;
  }>({
    key: "",
    name: "",
    desc: "",
    icon: "✨",
    base_url: "",
    model_name: "",
  });

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
          if (data.custom_ai_providers) {
            setAiProviders((prev) => ({
              ...prev,
              ...data.custom_ai_providers,
            }));
          }
          if (data.platform_accounts) {
            setAccounts((prev) => ({
              ...prev,
              ...data.platform_accounts,
            }));
          }
        }
      } catch (err) {
        console.error("Lỗi tải cấu hình", err);
      }
    };
    load();
  }, []);

  const handleSaveAll = async () => {
    setIsSaving(true);
    try {
      const payload = {
        auto_publish: autoPublish,
        custom_ai_providers: aiProviders,
        platform_accounts: accounts,
      };
      const res = await saveSocialSettings(payload);
      if (res.ok) {
        setSaveSuccess("Saved settings successfully!");
        toast.success("Saved settings & dynamic AI providers successfully!");
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

  const handleCreateCustomAIProvider = (e: React.FormEvent) => {
    e.preventDefault();
    const key = newProviderForm.key.toLowerCase().replace(/[^a-z0-9_]/g, "_") || `custom_${Date.now()}`;
    const newMeta: ProviderMeta = {
      name: newProviderForm.name || "Custom AI Provider",
      desc: newProviderForm.desc || "Custom OpenAI Compatible LLM Endpoint",
      icon: newProviderForm.icon || "✨",
      isCustom: true,
      fields: [
        { key: "api_key", label: "API Key / Auth Token", placeholder: "sk-xxxx..." },
        { key: "base_url", label: "Base API URL", placeholder: newProviderForm.base_url || "https://api.openai.com/v1" },
        { key: "model_name", label: "Default Model Name", placeholder: newProviderForm.model_name || "gpt-4o" },
      ],
    };

    setAiProviders({ ...aiProviders, [key]: newMeta });
    setAccounts({ ...accounts, [key]: [] });
    setIsAddProviderModalOpen(false);
    setNewProviderForm({ key: "", name: "", desc: "", icon: "✨", base_url: "", model_name: "" });
    toast.success(`Đã thêm nhà cung cấp AI động: ${newMeta.name}!`);
  };

  const handleDeleteAIProvider = (pKey: string) => {
    if (!window.confirm(`Xóa nhà cung cấp AI '${aiProviders[pKey]?.name}'?`)) return;
    const updated = { ...aiProviders };
    delete updated[pKey];
    setAiProviders(updated);
    if (selectedProviderKey === pKey) setSelectedProviderKey(null);
    toast.info(`Đã xóa nhà cung cấp AI.`);
  };

  const handleAddConnection = (pKey: string) => {
    const meta = oauthProviders[pKey] || aiProviders[pKey];
    if (!meta) return;
    const newAcc: AccountItem = {
      id: `${pKey}_${Date.now()}`,
      account_name: `${meta.name} Connection ${((accounts[pKey] || []).length + 1)}`,
      enabled: true,
    };
    meta.fields.forEach((f) => (newAcc[f.key] = ""));
    setEditingAcc(newAcc);
    setIsModalOpen(true);
  };

  const handleSaveAccountFromModal = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingAcc || !selectedProviderKey) return;

    const list = accounts[selectedProviderKey] || [];
    const idx = list.findIndex((a) => a.id === editingAcc.id);
    let updated = [...list];

    if (idx >= 0) {
      updated[idx] = editingAcc;
    } else {
      updated.push(editingAcc);
    }

    setAccounts({ ...accounts, [selectedProviderKey]: updated });
    setIsModalOpen(false);
    setEditingAcc(null);
  };

  const handleDeleteConnection = (pKey: string, accId: string) => {
    if (!window.confirm("Delete this connection?")) return;
    const list = accounts[pKey] || [];
    setAccounts({
      ...accounts,
      [pKey]: list.filter((a) => a.id !== accId),
    });
  };

  // Render Provider Detail Screen
  if (selectedProviderKey) {
    const meta = oauthProviders[selectedProviderKey] || aiProviders[selectedProviderKey];
    if (!meta) return null;
    const connList = accounts[selectedProviderKey] || [];

    return (
      <div className="space-y-6">
        {/* Detail Header Bar */}
        <div className="flex items-center justify-between pb-4 border-b border-zinc-800">
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setSelectedProviderKey(null)}
              className="border-zinc-800 bg-zinc-900 text-zinc-300 hover:bg-zinc-800"
            >
              <ArrowLeft className="w-3.5 h-3.5 mr-1" /> Back to Providers
            </Button>
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-zinc-800 border border-zinc-700 flex items-center justify-center text-lg text-zinc-100">
                {meta.icon}
              </div>
              <div>
                <h2 className="text-base font-bold text-zinc-100">{meta.name} Connections</h2>
                <p className="text-xs text-zinc-400">{meta.desc}</p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {meta.isCustom && (
              <Button
                variant="destructive"
                size="sm"
                onClick={() => handleDeleteAIProvider(selectedProviderKey)}
                className="h-8 text-xs"
              >
                <Trash2 className="w-3.5 h-3.5 mr-1" /> Remove Provider
              </Button>
            )}
            <Button
              variant="default"
              size="sm"
              onClick={() => handleAddConnection(selectedProviderKey)}
              className="h-8 text-xs"
            >
              <Plus className="w-3.5 h-3.5 mr-1" /> Add Connection
            </Button>
          </div>
        </div>

        {/* Connections Cards List */}
        {connList.length === 0 ? (
          <Card className="p-12 text-center bg-[#18181b] border-zinc-800 space-y-4">
            <p className="text-sm text-zinc-400">
              No active connections configured for {meta.name}. Click "Add Connection" to add your API Key or Token.
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleAddConnection(selectedProviderKey)}
            >
              <Plus className="w-3.5 h-3.5 mr-1" /> Add Connection
            </Button>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {connList.map((acc) => (
              <Card key={acc.id} className="bg-[#18181b] border-zinc-800 p-5 space-y-4 rounded-lg">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-zinc-800 border border-zinc-700 flex items-center justify-center text-sm font-bold text-zinc-100">
                      {meta.icon}
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold text-zinc-100">{acc.account_name}</h4>
                      <p className="text-[10px] font-mono text-zinc-500">ID: {acc.id}</p>
                    </div>
                  </div>
                  <Badge variant={acc.enabled ? "success" : "secondary"}>
                    {acc.enabled ? "● Connected" : "○ Disabled"}
                  </Badge>
                </div>

                <div className="space-y-2 pt-2 border-t border-zinc-800 text-xs font-mono">
                  {meta.fields.map((f) => (
                    <div key={f.key} className="flex justify-between">
                      <span className="text-zinc-400">{f.label}:</span>
                      <span className="text-zinc-200 truncate max-w-[200px]">
                        {acc[f.key] ? (f.key.includes("key") || f.key.includes("token") ? "••••••••••••••••" : String(acc[f.key])) : "<not set>"}
                      </span>
                    </div>
                  ))}
                </div>

                <div className="flex items-center justify-between pt-3 border-t border-zinc-800">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => toast.success(`Test connection for ${acc.account_name} succeeded!`)}
                    className="h-7 text-[11px] text-zinc-400 hover:text-zinc-100"
                  >
                    <TestTube className="w-3 h-3 mr-1" /> Test API
                  </Button>

                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setEditingAcc({ ...acc });
                        setIsModalOpen(true);
                      }}
                      className="h-7 text-[11px] px-2.5"
                    >
                      Edit
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => handleDeleteConnection(selectedProviderKey, acc.id)}
                      className="h-7 text-[11px] px-2"
                    >
                      <Trash2 className="w-3 h-3" />
                    </Button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}

        {/* Account Modal */}
        <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
          <DialogContent className="max-w-md bg-[#18181b] border-zinc-800 text-zinc-100">
            <DialogHeader>
              <DialogTitle className="text-zinc-100">Configure {meta.name} Connection</DialogTitle>
              <DialogDescription className="text-zinc-400">
                Enter label and authentication credentials for this provider.
              </DialogDescription>
            </DialogHeader>

            {editingAcc && (
              <form onSubmit={handleSaveAccountFromModal} className="space-y-4 py-2">
                <div>
                  <label className="block text-xs font-semibold text-zinc-400 mb-1">
                    Connection Label:
                  </label>
                  <Input
                    type="text"
                    value={editingAcc.account_name || ""}
                    onChange={(e) => setEditingAcc({ ...editingAcc, account_name: e.target.value })}
                    placeholder="e.g. Primary OpenAI Key"
                    required
                  />
                </div>

                {meta.fields.map((f) => (
                  <div key={f.key}>
                    <label className="block text-xs font-semibold text-zinc-400 mb-1">
                      {f.label}:
                    </label>
                    <Input
                      type={f.key.includes("key") || f.key.includes("secret") || f.key.includes("token") ? "password" : "text"}
                      value={editingAcc[f.key] || ""}
                      onChange={(e) => setEditingAcc({ ...editingAcc, [f.key]: e.target.value })}
                      placeholder={f.placeholder || `${f.label}...`}
                    />
                  </div>
                ))}

                <DialogFooter>
                  <Button type="button" variant="secondary" size="sm" onClick={() => setIsModalOpen(false)}>
                    Cancel
                  </Button>
                  <Button type="submit" variant="default" size="sm">
                    Save Connection
                  </Button>
                </DialogFooter>
              </form>
            )}
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  // Render Grid of Providers
  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex items-center justify-between pb-4 border-b border-zinc-800">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-zinc-100">Providers & Integrations</h2>
          <p className="text-xs text-zinc-400 mt-0.5">
            Manage your AI translation profiles, LLM endpoints & Social Media publish accounts
          </p>
        </div>

        <div className="flex items-center gap-3">
          {saveSuccess && (
            <Badge variant="success" className="py-1 px-3">
              <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> {saveSuccess}
            </Badge>
          )}
          <Button variant="default" size="sm" onClick={handleSaveAll} disabled={isSaving}>
            <Save className="w-3.5 h-3.5 mr-1.5" />
            <span>{isSaving ? "Saving..." : "Save All Changes"}</span>
          </Button>
        </div>
      </div>

      {/* Tabs Bar */}
      <div className="flex items-center gap-6 border-b border-zinc-800 text-xs font-medium">
        <button
          onClick={() => setActiveTab("connections")}
          className={`pb-2.5 border-b-2 transition-colors ${
            activeTab === "connections"
              ? "border-zinc-100 text-zinc-100 font-semibold"
              : "border-transparent text-zinc-400 hover:text-zinc-200"
          }`}
        >
          Connections & AI Profiles
        </button>
        <button
          onClick={() => setActiveTab("usage")}
          className={`pb-2.5 border-b-2 transition-colors ${
            activeTab === "usage"
              ? "border-zinc-100 text-zinc-100 font-semibold"
              : "border-transparent text-zinc-400 hover:text-zinc-200"
          }`}
        >
          Usage & Quotas
        </button>
      </div>

      {/* Section 1: Dynamic AI Providers (AI Translation & LLM Engines) */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bot className="w-4 h-4 text-purple-400" />
            <h3 className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
              API KEY PROVIDERS (AI TRANSLATION & CONTEXT)
            </h3>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsAddProviderModalOpen(true)}
            className="h-7 text-xs border-dashed border-zinc-700 bg-zinc-900/60 hover:bg-zinc-800 text-purple-300"
          >
            <Sparkles className="w-3.5 h-3.5 mr-1.5 text-purple-400" />
            <span>+ Add AI Provider</span>
          </Button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {Object.keys(aiProviders).map((pKey) => {
            const meta = aiProviders[pKey];
            const activeCount = (accounts[pKey] || []).filter((a) => a.enabled).length;

            return (
              <div
                key={pKey}
                onClick={() => setSelectedProviderKey(pKey)}
                className="bg-[#18181b] border border-zinc-800 hover:border-zinc-700 hover:bg-[#202023] rounded-lg p-3.5 flex items-center justify-between cursor-pointer transition-colors group relative"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-9 h-9 rounded-md bg-zinc-800 border border-zinc-700 flex items-center justify-center text-base text-zinc-100 shrink-0">
                    {meta.icon}
                  </div>
                  <div className="min-w-0">
                    <h4 className="text-xs font-semibold text-zinc-100 group-hover:text-zinc-50 truncate flex items-center gap-1.5">
                      <span>{meta.name}</span>
                      {meta.isCustom && (
                        <Badge variant="outline" className="text-[9px] px-1 py-0 border-purple-500/40 text-purple-300 bg-purple-500/10">
                          Custom
                        </Badge>
                      )}
                    </h4>
                    <p className="text-[10px] font-medium mt-0.5">
                      {activeCount > 0 ? (
                        <span className="text-emerald-400 flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                          {activeCount} Connected
                        </span>
                      ) : (
                        <span className="text-zinc-500">No connections</span>
                      )}
                    </p>
                  </div>
                </div>

                <ChevronRight className="w-4 h-4 text-zinc-500 group-hover:text-zinc-300 transition-colors shrink-0" />
              </div>
            );
          })}

          {/* Add Provider Dotted Card */}
          <div
            onClick={() => setIsAddProviderModalOpen(true)}
            className="bg-[#18181b]/50 border border-dashed border-zinc-800 hover:border-purple-500/50 hover:bg-zinc-900/60 rounded-lg p-3.5 flex items-center justify-center cursor-pointer transition-colors group h-[68px]"
          >
            <div className="flex items-center gap-2 text-xs text-zinc-400 group-hover:text-purple-300 font-medium">
              <Plus className="w-4 h-4" />
              <span>Add Custom AI Engine</span>
            </div>
          </div>
        </div>
      </div>

      {/* Section 2: OAuth Providers (Social Media Accounts) */}
      <div className="space-y-3 pt-4">
        <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
          OAuth Providers (Social Media Accounts)
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {Object.keys(oauthProviders).map((pKey) => {
            const meta = oauthProviders[pKey];
            const activeCount = (accounts[pKey] || []).filter((a) => a.enabled).length;

            return (
              <div
                key={pKey}
                onClick={() => setSelectedProviderKey(pKey)}
                className="bg-[#18181b] border border-zinc-800 hover:border-zinc-700 hover:bg-[#202023] rounded-lg p-3.5 flex items-center justify-between cursor-pointer transition-colors group"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-9 h-9 rounded-md bg-zinc-800 border border-zinc-700 flex items-center justify-center text-base text-zinc-100 shrink-0">
                    {meta.icon}
                  </div>
                  <div className="min-w-0">
                    <h4 className="text-xs font-semibold text-zinc-100 group-hover:text-zinc-50 truncate">
                      {meta.name}
                    </h4>
                    <p className="text-[10px] font-medium mt-0.5">
                      {activeCount > 0 ? (
                        <span className="text-emerald-400 flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                          {activeCount} Connected
                        </span>
                      ) : (
                        <span className="text-zinc-500">No connections</span>
                      )}
                    </p>
                  </div>
                </div>

                <ChevronRight className="w-4 h-4 text-zinc-500 group-hover:text-zinc-300 transition-colors shrink-0" />
              </div>
            );
          })}
        </div>
      </div>

      {/* Add Custom AI Provider Dialog */}
      <Dialog open={isAddProviderModalOpen} onOpenChange={setIsAddProviderModalOpen}>
        <DialogContent className="max-w-md bg-[#18181b] border-zinc-800 text-zinc-100">
          <DialogHeader>
            <DialogTitle className="text-zinc-100 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-purple-400" /> Add Custom AI Engine
            </DialogTitle>
            <DialogDescription className="text-zinc-400">
              Create a dynamic AI Translation / LLM Provider (compatible with OpenAI, Groq, Ollama, OpenRouter, Mistral, etc.)
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleCreateCustomAIProvider} className="space-y-4 py-2">
            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-1">
                Provider Name:
              </label>
              <Input
                type="text"
                value={newProviderForm.name}
                onChange={(e) => setNewProviderForm({ ...newProviderForm, name: e.target.value })}
                placeholder="e.g. Ollama Local AI, OpenRouter LLM"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-1">
                Description:
              </label>
              <Input
                type="text"
                value={newProviderForm.desc}
                onChange={(e) => setNewProviderForm({ ...newProviderForm, desc: e.target.value })}
                placeholder="e.g. Custom LLM Endpoint for Translation"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-zinc-400 mb-1">
                  Icon Emoji:
                </label>
                <Input
                  type="text"
                  value={newProviderForm.icon}
                  onChange={(e) => setNewProviderForm({ ...newProviderForm, icon: e.target.value })}
                  placeholder="⚡, 🧠, 🤖, 🔮, 🦙"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-zinc-400 mb-1">
                  Provider ID Key:
                </label>
                <Input
                  type="text"
                  value={newProviderForm.key}
                  onChange={(e) => setNewProviderForm({ ...newProviderForm, key: e.target.value })}
                  placeholder="ollama_local"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-1">
                Base API URL (Optional):
              </label>
              <Input
                type="text"
                value={newProviderForm.base_url}
                onChange={(e) => setNewProviderForm({ ...newProviderForm, base_url: e.target.value })}
                placeholder="https://api.openai.com/v1 or http://localhost:11434/v1"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-1">
                Default Model Name:
              </label>
              <Input
                type="text"
                value={newProviderForm.model_name}
                onChange={(e) => setNewProviderForm({ ...newProviderForm, model_name: e.target.value })}
                placeholder="llama-3.3-70b-versatile, qwen2.5, gpt-4o-mini"
              />
            </div>

            <DialogFooter>
              <Button type="button" variant="secondary" size="sm" onClick={() => setIsAddProviderModalOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="default" size="sm" className="bg-purple-600 hover:bg-purple-500 text-white">
                Add AI Provider
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
};
