"use client";

import { useMemo, useState } from "react";
import {
  ChevronDown,
  CircleDot,
  Eye,
  EyeOff,
  Plus,
  Settings2,
  Trash2,
} from "lucide-react";
import { useActiveWorkspaceModels, useWorkspace } from "@/components/providers/WorkspaceProvider";
import {
  createNewEmbeddingModel,
  createNewEmbeddingProfile,
  createNewLlmModel,
  createNewLlmProfile,
  createNewRerankerModel,
  createNewRerankerProfile,
  getProviderOption,
  PROVIDER_OPTIONS,
} from "@/lib/runtime";
import type {
  DiagnosticResult,
  EmbeddingModelEntry,
  EmbeddingProfile,
  LLMModelEntry,
  LLMProfile,
  RerankerModelEntry,
  RerankerProfile,
} from "@/lib/types";

type SettingsTab = "llm" | "embedding" | "reranker";

function SummaryCard({
  title,
  headline,
  subline,
  online,
}: {
  title: string;
  headline: string;
  subline: string;
  online: boolean;
}) {
  return (
    <div className="h-full rounded-[22px] border border-[var(--border)] bg-[var(--card)] px-5 py-5">
      <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
        <span
          className={`h-2.5 w-2.5 rounded-full ${
            online ? "bg-emerald-500" : "bg-rose-400"
          }`}
        />
        {title}
      </div>
      <div className="mt-4 text-[22px] font-semibold tracking-tight text-[var(--foreground)]">
        {headline}
      </div>
      <div className="mt-2 text-sm leading-6 text-[var(--muted-foreground)]">
        {subline}
      </div>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-xs font-medium tracking-[0.04em] text-[var(--muted-foreground)]">
      {children}
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string | number;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: "text" | "password" | "number";
}) {
  return (
    <label className="grid gap-2 text-sm text-[var(--foreground)]">
      <SectionLabel>{label}</SectionLabel>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className="h-12 rounded-[14px] border border-[var(--border)] bg-[var(--background)] px-4 text-sm outline-none transition focus:border-[var(--ring)]"
      />
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-2 text-sm text-[var(--foreground)]">
      <SectionLabel>{label}</SectionLabel>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-12 rounded-[14px] border border-[var(--border)] bg-[var(--background)] px-4 text-sm outline-none transition focus:border-[var(--ring)]"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function DiagnosticsConsole({ result }: { result: DiagnosticResult | null }) {
  const text = useMemo(() => {
    if (!result) {
      return "Waiting for test run...";
    }
    const lines = [
      `[${result.status === "ok" ? "PASS" : "FAIL"}] ${result.kind.toUpperCase()} ${result.model_id}`,
      `provider: ${getProviderOption(result.provider).label} (${result.provider})`,
      `profile: ${result.profile_name}`,
    ];
    if (result.latency_ms !== undefined) {
      lines.push(`latency_ms: ${result.latency_ms}`);
    }
    if (result.request_preview) {
      lines.push("");
      lines.push("request_preview:");
      lines.push(JSON.stringify(result.request_preview, null, 2));
    }
    if (result.contract_summary) {
      lines.push("");
      lines.push("contract_summary:");
      lines.push(JSON.stringify(result.contract_summary, null, 2));
    }
    if (result.response_preview) {
      lines.push("");
      lines.push("response_preview:");
      lines.push(result.response_preview);
    }
    if (result.error) {
      lines.push("");
      lines.push("error:");
      lines.push(result.error);
    }
    return lines.join("\n");
  }, [result]);

  return (
    <pre className="min-h-[136px] overflow-x-auto rounded-[14px] bg-[#111111] px-4 py-4 text-xs leading-6 text-stone-100">
      {text}
    </pre>
  );
}

export function SettingsWorkspace() {
  const {
    settings,
    backendHealthy,
    diagnostics,
    runtimeError,
    lastError,
    runDiagnostic,
    rebuildRetrieval,
    updateSettings,
    clearLastError,
  } = useWorkspace();
  const {
    llmProfile,
    llmModel,
    embeddingProfile,
    embeddingModel,
    rerankerProfile,
    rerankerModel,
  } =
    useActiveWorkspaceModels();
  const [activeTab, setActiveTab] = useState<SettingsTab>("llm");
  const [showLlmKey, setShowLlmKey] = useState(false);
  const [showEmbeddingKey, setShowEmbeddingKey] = useState(false);
  const [showRerankerKey, setShowRerankerKey] = useState(false);
  const hasLlmProfile = Boolean(llmProfile && llmModel);
  const hasEmbeddingProfile = Boolean(embeddingProfile && embeddingModel);
  const hasRerankerProfile = Boolean(rerankerProfile && rerankerModel);
  const providerOptions = PROVIDER_OPTIONS.map((item) => ({
    value: item.id,
    label: item.label,
  }));

  const updateLlmProfile = (profileId: string, patch: Partial<LLMProfile>) => {
    updateSettings((current) => ({
      ...current,
      llmProfiles: current.llmProfiles.map((item) =>
        item.id === profileId ? { ...item, ...patch } : item,
      ),
    }));
  };

  const updateEmbeddingProfile = (
    profileId: string,
    patch: Partial<EmbeddingProfile>,
  ) => {
    updateSettings((current) => ({
      ...current,
      embeddingProfiles: current.embeddingProfiles.map((item) =>
        item.id === profileId ? { ...item, ...patch } : item,
      ),
    }));
  };

  const updateRerankerProfile = (
    profileId: string,
    patch: Partial<RerankerProfile>,
  ) => {
    updateSettings((current) => ({
      ...current,
      rerankerProfiles: current.rerankerProfiles.map((item) =>
        item.id === profileId ? { ...item, ...patch } : item,
      ),
    }));
  };

  const changeLlmProvider = (value: string) => {
    if (!llmProfile) return;
    const currentPreset = getProviderOption(llmProfile.provider);
    const nextPreset = getProviderOption(value);
    const shouldRewriteBaseUrl =
      !llmProfile.baseUrl || llmProfile.baseUrl === currentPreset.llmBaseUrl;
    updateLlmProfile(llmProfile.id, {
      provider: nextPreset.id,
      baseUrl: shouldRewriteBaseUrl ? nextPreset.llmBaseUrl : llmProfile.baseUrl,
    });
  };

  const changeEmbeddingProvider = (value: string) => {
    if (!embeddingProfile) return;
    const currentPreset = getProviderOption(embeddingProfile.provider);
    const nextPreset = getProviderOption(value);
    const shouldRewriteEndpoint =
      !embeddingProfile.endpointUrl ||
      embeddingProfile.endpointUrl === currentPreset.embeddingEndpointUrl;
    updateEmbeddingProfile(embeddingProfile.id, {
      provider: nextPreset.id,
      endpointUrl: shouldRewriteEndpoint
        ? nextPreset.embeddingEndpointUrl
        : embeddingProfile.endpointUrl,
    });
  };

  const changeRerankerProvider = (value: string) => {
    if (!rerankerProfile) return;
    const currentPreset = getProviderOption(rerankerProfile.provider);
    const nextPreset = getProviderOption(value);
    const shouldRewriteEndpoint =
      !rerankerProfile.endpointUrl ||
      rerankerProfile.endpointUrl === currentPreset.rerankerEndpointUrl;
    updateRerankerProfile(rerankerProfile.id, {
      provider: nextPreset.id,
      endpointUrl: shouldRewriteEndpoint
        ? nextPreset.rerankerEndpointUrl
        : rerankerProfile.endpointUrl,
    });
  };

  const updateLlmModel = (modelId: string, patch: Partial<LLMModelEntry>) => {
    updateSettings((current) => ({
      ...current,
      llmProfiles: current.llmProfiles.map((profile) =>
        profile.id !== current.activeLlmProfileId
          ? profile
          : {
              ...profile,
              models: profile.models.map((model) =>
                model.id === modelId ? { ...model, ...patch } : model,
              ),
            },
      ),
    }));
  };

  const updateEmbeddingModel = (
    modelId: string,
    patch: Partial<EmbeddingModelEntry>,
  ) => {
    updateSettings((current) => ({
      ...current,
      embeddingProfiles: current.embeddingProfiles.map((profile) =>
        profile.id !== current.activeEmbeddingProfileId
          ? profile
          : {
              ...profile,
              models: profile.models.map((model) =>
                model.id === modelId ? { ...model, ...patch } : model,
              ),
            },
      ),
    }));
  };

  const updateRerankerModel = (
    modelId: string,
    patch: Partial<RerankerModelEntry>,
  ) => {
    updateSettings((current) => ({
      ...current,
      rerankerProfiles: current.rerankerProfiles.map((profile) =>
        profile.id !== current.activeRerankerProfileId
          ? profile
          : {
              ...profile,
              models: profile.models.map((model) =>
                model.id === modelId ? { ...model, ...patch } : model,
              ),
            },
      ),
    }));
  };

  const removeLlmProfile = () => {
    if (!llmProfile) return;
    if (settings.llmProfiles.length <= 1) return;
    updateSettings((current) => {
      const nextProfiles = current.llmProfiles.filter(
        (profile) => profile.id !== current.activeLlmProfileId,
      );
      return {
        ...current,
        llmProfiles: nextProfiles,
        activeLlmProfileId: nextProfiles[0].id,
      };
    });
  };

  const removeEmbeddingProfile = () => {
    if (!embeddingProfile) return;
    if (settings.embeddingProfiles.length <= 1) return;
    updateSettings((current) => {
      const nextProfiles = current.embeddingProfiles.filter(
        (profile) => profile.id !== current.activeEmbeddingProfileId,
      );
      return {
        ...current,
        embeddingProfiles: nextProfiles,
        activeEmbeddingProfileId: nextProfiles[0].id,
      };
    });
  };

  const removeRerankerProfile = () => {
    if (!rerankerProfile) return;
    if (settings.rerankerProfiles.length <= 1) return;
    updateSettings((current) => {
      const nextProfiles = current.rerankerProfiles.filter(
        (profile) => profile.id !== current.activeRerankerProfileId,
      );
      return {
        ...current,
        rerankerProfiles: nextProfiles,
        activeRerankerProfileId: nextProfiles[0].id,
      };
    });
  };

  const addLlmModel = () => {
    if (!llmProfile) return;
    const model = createNewLlmModel();
    updateSettings((current) => ({
      ...current,
      llmProfiles: current.llmProfiles.map((profile) =>
        profile.id !== current.activeLlmProfileId
          ? profile
          : {
              ...profile,
              models: [...profile.models, model],
              activeModelId: model.id,
            },
      ),
    }));
  };

  const addEmbeddingModel = () => {
    if (!embeddingProfile) return;
    const model = createNewEmbeddingModel();
    updateSettings((current) => ({
      ...current,
      embeddingProfiles: current.embeddingProfiles.map((profile) =>
        profile.id !== current.activeEmbeddingProfileId
          ? profile
          : {
              ...profile,
              models: [...profile.models, model],
              activeModelId: model.id,
            },
      ),
    }));
  };

  const addRerankerModel = () => {
    if (!rerankerProfile) return;
    const model = createNewRerankerModel();
    updateSettings((current) => ({
      ...current,
      rerankerProfiles: current.rerankerProfiles.map((profile) =>
        profile.id !== current.activeRerankerProfileId
          ? profile
          : {
              ...profile,
              models: [...profile.models, model],
              activeModelId: model.id,
            },
      ),
    }));
  };

  const removeLlmModel = () => {
    if (!llmProfile || !llmModel) return;
    if (llmProfile!.models.length <= 1) return;
    updateSettings((current) => ({
      ...current,
      llmProfiles: current.llmProfiles.map((profile) =>
        profile.id !== current.activeLlmProfileId
          ? profile
          : {
              ...profile,
              models: profile.models.filter((model) => model.id !== profile.activeModelId),
              activeModelId:
                profile.models.find((model) => model.id !== profile.activeModelId)?.id ||
                profile.models[0].id,
            },
      ),
    }));
  };

  const removeEmbeddingModel = () => {
    if (!embeddingProfile || !embeddingModel) return;
    if (embeddingProfile!.models.length <= 1) return;
    updateSettings((current) => ({
      ...current,
      embeddingProfiles: current.embeddingProfiles.map((profile) =>
        profile.id !== current.activeEmbeddingProfileId
          ? profile
          : {
              ...profile,
              models: profile.models.filter((model) => model.id !== profile.activeModelId),
              activeModelId:
                profile.models.find((model) => model.id !== profile.activeModelId)?.id ||
                profile.models[0].id,
            },
      ),
    }));
  };

  const removeRerankerModel = () => {
    if (!rerankerProfile || !rerankerModel) return;
    if (rerankerProfile.models.length <= 1) return;
    updateSettings((current) => ({
      ...current,
      rerankerProfiles: current.rerankerProfiles.map((profile) =>
        profile.id !== current.activeRerankerProfileId
          ? profile
          : {
              ...profile,
              models: profile.models.filter((model) => model.id !== profile.activeModelId),
              activeModelId:
                profile.models.find((model) => model.id !== profile.activeModelId)?.id ||
                profile.models[0].id,
            },
      ),
    }));
  };

  return (
    <div className="min-h-screen bg-[var(--background)] px-8 py-7">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          title="后端"
          headline={backendHealthy ? "在线" : "离线"}
          subline={backendHealthy ? "FastAPI 服务可达" : "等待本地后端启动"}
          online={backendHealthy}
        />
        <SummaryCard
          title="LLM"
          headline={llmModel?.label || "未配置"}
          subline={llmProfile?.name || "创建第一个对话配置后显示"}
          online={Boolean(llmProfile && llmProfile.provider !== "mock")}
        />
        <SummaryCard
          title="嵌入模型"
          headline={embeddingModel?.label || "未配置"}
          subline={embeddingProfile?.name || "创建第一个向量配置后显示"}
          online={Boolean(embeddingProfile && embeddingProfile.provider !== "mock")}
        />
        <SummaryCard
          title="重排模型"
          headline={rerankerModel?.label || "LLM fallback"}
          subline={rerankerProfile?.name || "创建第一个重排配置后显示"}
          online={Boolean(rerankerProfile && rerankerProfile.provider !== "mock")}
        />
      </div>

      <div className="mt-6 flex items-center gap-3 border-b border-[var(--border)] pb-3">
        {[
          ["llm", `LLM ${settings.llmProfiles.length}`],
          ["embedding", `EMBEDDING ${settings.embeddingProfiles.length}`],
          ["reranker", `RERANKER ${settings.rerankerProfiles.length}`],
        ].map(([key, label]) => {
          const active = activeTab === key;
          const Icon = Settings2;
          return (
            <button
              key={key}
              onClick={() => setActiveTab(key as SettingsTab)}
              className={`inline-flex h-10 items-center gap-2 rounded-[12px] px-4 text-sm transition ${
                active
                  ? "bg-[var(--secondary)] text-[var(--foreground)]"
                  : "text-[var(--muted-foreground)] hover:bg-[var(--secondary)]/70"
              }`}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          );
        })}
      </div>

      <div className="mt-4 grid gap-5 xl:grid-cols-[270px_minmax(0,1fr)]">
        {activeTab === "llm" ? (
          <>
            <aside className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="text-sm font-medium text-[var(--foreground)]">
                  配置文件
                </div>
                <button
                  onClick={() =>
                    updateSettings((current) => {
                      const profile = createNewLlmProfile();
                      return {
                        ...current,
                        llmProfiles: [...current.llmProfiles, profile],
                        activeLlmProfileId: profile.id,
                      };
                    })
                  }
                  className="inline-flex h-9 items-center gap-1 rounded-[12px] border border-[var(--border)] px-3 text-sm"
                >
                  <Plus className="h-4 w-4" />
                  配置文件
                </button>
              </div>
              <div className="rounded-[18px] border border-[var(--border)] bg-[var(--card)] px-4 py-3">
                <div className="space-y-4">
                  {settings.llmProfiles.map((profile) => {
                    const active = profile.id === settings.activeLlmProfileId;
                    const currentModel =
                      profile.models.find((model) => model.id === profile.activeModelId) ||
                      profile.models[0];
                    return (
                      <button
                        key={profile.id}
                        onClick={() =>
                          updateSettings((current) => ({
                            ...current,
                            activeLlmProfileId: profile.id,
                          }))
                        }
                        className={`block w-full border-b border-[var(--border)] pb-4 text-left last:border-0 last:pb-0 ${
                          active ? "text-[var(--foreground)]" : "text-[var(--muted-foreground)]"
                        }`}
                      >
                        <div className="text-[17px] font-semibold tracking-tight">
                          {profile.name}
                        </div>
                        <div className="mt-1 truncate text-xs">{profile.baseUrl}</div>
                        <div className="mt-3 text-xs">
                          当前模型
                        </div>
                        <div className="mt-1 text-sm font-medium">{currentModel.label}</div>
                      </button>
                    );
                  })}
                </div>
                <button
                  onClick={removeLlmProfile}
                  className="mt-5 inline-flex items-center gap-2 text-sm text-[var(--muted-foreground)]"
                >
                  <Trash2 className="h-4 w-4" />
                  删除配置文件
                </button>
              </div>
            </aside>

            <div className="space-y-5">
              {!hasLlmProfile ? (
                <section className="rounded-[18px] border border-dashed border-[var(--border)] bg-[var(--card)] px-5 py-8">
                  <div className="text-lg font-semibold tracking-tight">还没有 LLM 配置</div>
                  <div className="mt-2 max-w-2xl text-sm leading-7 text-[var(--muted-foreground)]">
                    这里保持空白，等你自己创建配置文件并填入提供商、Base URL、API Key 和模型 ID
                    之后，诊断和真实对话才会开始使用它。
                  </div>
                </section>
              ) : (
                <>
              <section className="rounded-[18px] border border-[var(--border)] bg-[var(--card)] px-5 py-5">
                <div className="mb-5 text-lg font-semibold tracking-tight">配置文件</div>
                <div className="grid gap-4 md:grid-cols-2">
                  <TextField
                    label="名称"
                    value={llmProfile!.name}
                    onChange={(value) => updateLlmProfile(llmProfile!.id, { name: value })}
                  />
                  <SelectField
                    label="提供商"
                    value={llmProfile!.provider}
                    options={providerOptions}
                    onChange={changeLlmProvider}
                  />
                </div>
                <div className="mt-4">
                  <TextField
                    label="Base URL"
                    value={llmProfile!.baseUrl}
                    onChange={(value) => updateLlmProfile(llmProfile!.id, { baseUrl: value })}
                  />
                </div>
                <div className="mt-4 grid gap-4 md:grid-cols-[minmax(0,1fr)_48px]">
                  <TextField
                    label="API Key"
                    value={llmProfile!.apiKey}
                    type={showLlmKey ? "text" : "password"}
                    onChange={(value) => updateLlmProfile(llmProfile!.id, { apiKey: value })}
                  />
                  <button
                    onClick={() => setShowLlmKey((value) => !value)}
                    className="mt-[26px] inline-flex h-12 items-center justify-center rounded-[14px] border border-[var(--border)] bg-[var(--background)]"
                  >
                    {showLlmKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <TextField
                    label="API 版本"
                    value={llmProfile!.apiVersion}
                    placeholder="可选"
                    onChange={(value) => updateLlmProfile(llmProfile!.id, { apiVersion: value })}
                  />
                  <label className="grid gap-2 text-sm text-[var(--foreground)]">
                    <SectionLabel>额外请求头 (JSON)</SectionLabel>
                    <textarea
                      value={llmProfile!.extraHeadersText}
                      onChange={(event) =>
                        updateLlmProfile(llmProfile!.id, { extraHeadersText: event.target.value })
                      }
                      className="min-h-[112px] rounded-[14px] border border-[var(--border)] bg-[var(--background)] px-4 py-3 text-sm outline-none transition focus:border-[var(--ring)]"
                    />
                  </label>
                </div>
              </section>

              <section className="rounded-[18px] border border-[var(--border)] bg-[var(--card)] px-5 py-5">
                <div className="mb-4 flex items-center justify-between">
                  <div className="text-lg font-semibold tracking-tight">模型列表</div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={addLlmModel}
                      className="inline-flex h-9 items-center gap-1 rounded-[12px] border border-[var(--border)] px-3 text-sm"
                    >
                      <Plus className="h-4 w-4" />
                      模型
                    </button>
                    <button
                      onClick={removeLlmModel}
                      className="inline-flex h-9 items-center gap-1 rounded-[12px] text-sm text-[var(--muted-foreground)]"
                    >
                      <Trash2 className="h-4 w-4" />
                      删除
                    </button>
                  </div>
                </div>
                <div className="mb-4 flex flex-wrap gap-2">
                  {llmProfile!.models.map((model) => {
                    const active = model.id === llmProfile!.activeModelId;
                    return (
                      <button
                        key={model.id}
                        onClick={() =>
                          updateLlmProfile(llmProfile!.id, { activeModelId: model.id })
                        }
                        className={`inline-flex h-9 items-center rounded-full px-4 text-sm ${
                          active
                            ? "bg-[#1e1b18] text-white"
                            : "bg-[var(--secondary)] text-[var(--foreground)]"
                        }`}
                      >
                        <CircleDot className="mr-2 h-4 w-4" />
                        {model.label}
                      </button>
                    );
                  })}
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <TextField
                    label="标签"
                    value={llmModel!.label}
                    onChange={(value) => updateLlmModel(llmModel!.id, { label: value })}
                  />
                  <TextField
                    label="模型 ID"
                    value={llmModel!.modelId}
                    onChange={(value) => updateLlmModel(llmModel!.id, { modelId: value })}
                  />
                  <TextField
                    label="上下文窗口"
                    value={llmModel!.contextWindow}
                    type="number"
                    onChange={(value) =>
                      updateLlmModel(llmModel!.id, {
                        contextWindow: Number(value || 0),
                      })
                    }
                  />
                  <label className="grid gap-2 text-sm text-[var(--foreground)]">
                    <SectionLabel>来源</SectionLabel>
                    <textarea
                      value={llmModel!.source}
                      onChange={(event) =>
                        updateLlmModel(llmModel!.id, { source: event.target.value })
                      }
                      className="min-h-[112px] rounded-[14px] border border-[var(--border)] bg-[var(--background)] px-4 py-3 text-sm outline-none transition focus:border-[var(--ring)]"
                    />
                  </label>
                </div>
              </section>
                </>
              )}
            </div>
          </>
        ) : null}

        {activeTab === "embedding" ? (
          <>
            <aside className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="text-sm font-medium text-[var(--foreground)]">
                  配置文件
                </div>
                <button
                  onClick={() =>
                    updateSettings((current) => {
                      const profile = createNewEmbeddingProfile();
                      return {
                        ...current,
                        embeddingProfiles: [...current.embeddingProfiles, profile],
                        activeEmbeddingProfileId: profile.id,
                      };
                    })
                  }
                  className="inline-flex h-9 items-center gap-1 rounded-[12px] border border-[var(--border)] px-3 text-sm"
                >
                  <Plus className="h-4 w-4" />
                  配置文件
                </button>
              </div>
              <div className="rounded-[18px] border border-[var(--border)] bg-[var(--card)] px-4 py-3">
                <div className="space-y-4">
                  {settings.embeddingProfiles.map((profile) => {
                    const active = profile.id === settings.activeEmbeddingProfileId;
                    const currentModel =
                      profile.models.find((model) => model.id === profile.activeModelId) ||
                      profile.models[0];
                    return (
                      <button
                        key={profile.id}
                        onClick={() =>
                          updateSettings((current) => ({
                            ...current,
                            activeEmbeddingProfileId: profile.id,
                          }))
                        }
                        className={`block w-full border-b border-[var(--border)] pb-4 text-left last:border-0 last:pb-0 ${
                          active ? "text-[var(--foreground)]" : "text-[var(--muted-foreground)]"
                        }`}
                      >
                        <div className="text-[17px] font-semibold tracking-tight">
                          {profile.name}
                        </div>
                        <div className="mt-1 truncate text-xs">{profile.endpointUrl}</div>
                        <div className="mt-3 text-xs">
                          当前模型
                        </div>
                        <div className="mt-1 text-sm font-medium">{currentModel.label}</div>
                      </button>
                    );
                  })}
                </div>
                <button
                  onClick={removeEmbeddingProfile}
                  className="mt-5 inline-flex items-center gap-2 text-sm text-[var(--muted-foreground)]"
                >
                  <Trash2 className="h-4 w-4" />
                  删除配置文件
                </button>
              </div>
            </aside>

            <div className="space-y-5">
              {!hasEmbeddingProfile ? (
                <section className="rounded-[18px] border border-dashed border-[var(--border)] bg-[var(--card)] px-5 py-8">
                  <div className="text-lg font-semibold tracking-tight">还没有 Embedding 配置</div>
                  <div className="mt-2 max-w-2xl text-sm leading-7 text-[var(--muted-foreground)]">
                    这里不会预填任何示例端点。等你自己创建向量配置并填入 endpoint、API Key、
                    模型 ID 和维度后，记忆检索与诊断才会真正使用它。
                  </div>
                </section>
              ) : (
                <>
              <section className="rounded-[18px] border border-[var(--border)] bg-[var(--card)] px-5 py-5">
                <div className="mb-5 text-lg font-semibold tracking-tight">配置文件</div>
                <div className="grid gap-4 md:grid-cols-2">
                  <TextField
                    label="名称"
                    value={embeddingProfile!.name}
                    onChange={(value) =>
                      updateEmbeddingProfile(embeddingProfile!.id, { name: value })
                    }
                  />
                  <SelectField
                    label="提供商"
                    value={embeddingProfile!.provider}
                    options={providerOptions}
                    onChange={changeEmbeddingProvider}
                  />
                </div>
                <div className="mt-4">
                  <TextField
                    label="Endpoint URL"
                    value={embeddingProfile!.endpointUrl}
                    onChange={(value) =>
                      updateEmbeddingProfile(embeddingProfile!.id, { endpointUrl: value })
                    }
                  />
                </div>
                <div className="mt-2 text-xs leading-6 text-[var(--muted-foreground)]">
                  Embedding 请求会被精确发送到这个 URL，不会在运行时额外拼接
                  `/embeddings`。
                </div>
                <div className="mt-4 grid gap-4 md:grid-cols-[minmax(0,1fr)_48px]">
                  <TextField
                    label="API Key"
                    value={embeddingProfile!.apiKey}
                    type={showEmbeddingKey ? "text" : "password"}
                    onChange={(value) =>
                      updateEmbeddingProfile(embeddingProfile!.id, { apiKey: value })
                    }
                  />
                  <button
                    onClick={() => setShowEmbeddingKey((value) => !value)}
                    className="mt-[26px] inline-flex h-12 items-center justify-center rounded-[14px] border border-[var(--border)] bg-[var(--background)]"
                  >
                    {showEmbeddingKey ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <TextField
                    label="API 版本"
                    value={embeddingProfile!.apiVersion}
                    placeholder="可选"
                    onChange={(value) =>
                      updateEmbeddingProfile(embeddingProfile!.id, { apiVersion: value })
                    }
                  />
                  <label className="grid gap-2 text-sm text-[var(--foreground)]">
                    <SectionLabel>额外请求头 (JSON)</SectionLabel>
                    <textarea
                      value={embeddingProfile!.extraHeadersText}
                      onChange={(event) =>
                        updateEmbeddingProfile(embeddingProfile!.id, {
                          extraHeadersText: event.target.value,
                        })
                      }
                      className="min-h-[112px] rounded-[14px] border border-[var(--border)] bg-[var(--background)] px-4 py-3 text-sm outline-none transition focus:border-[var(--ring)]"
                    />
                  </label>
                </div>
              </section>

              <section className="rounded-[18px] border border-[var(--border)] bg-[var(--card)] px-5 py-5">
                <div className="mb-4 flex items-center justify-between">
                  <div className="text-lg font-semibold tracking-tight">模型列表</div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={addEmbeddingModel}
                      className="inline-flex h-9 items-center gap-1 rounded-[12px] border border-[var(--border)] px-3 text-sm"
                    >
                      <Plus className="h-4 w-4" />
                      模型
                    </button>
                    <button
                      onClick={removeEmbeddingModel}
                      className="inline-flex h-9 items-center gap-1 rounded-[12px] text-sm text-[var(--muted-foreground)]"
                    >
                      <Trash2 className="h-4 w-4" />
                      删除
                    </button>
                  </div>
                </div>
                <div className="mb-4 flex flex-wrap gap-2">
                  {embeddingProfile!.models.map((model) => {
                    const active = model.id === embeddingProfile!.activeModelId;
                    return (
                      <button
                        key={model.id}
                        onClick={() =>
                          updateEmbeddingProfile(embeddingProfile!.id, {
                            activeModelId: model.id,
                          })
                        }
                        className={`inline-flex h-9 items-center rounded-full px-4 text-sm ${
                          active
                            ? "bg-[#1e1b18] text-white"
                            : "bg-[var(--secondary)] text-[var(--foreground)]"
                        }`}
                      >
                        <CircleDot className="mr-2 h-4 w-4" />
                        {model.label}
                      </button>
                    );
                  })}
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <TextField
                    label="标签"
                    value={embeddingModel!.label}
                    onChange={(value) =>
                      updateEmbeddingModel(embeddingModel!.id, { label: value })
                    }
                  />
                  <TextField
                    label="模型 ID"
                    value={embeddingModel!.modelId}
                    onChange={(value) =>
                      updateEmbeddingModel(embeddingModel!.id, { modelId: value })
                    }
                  />
                  <TextField
                    label="维度"
                    value={embeddingModel!.dimensions}
                    type="number"
                    onChange={(value) =>
                      updateEmbeddingModel(embeddingModel!.id, {
                        dimensions: Number(value || 0),
                      })
                    }
                  />
                  <label className="grid gap-2 text-sm text-[var(--foreground)]">
                    <SectionLabel>参数</SectionLabel>
                    <div className="flex h-12 items-center gap-3 rounded-[14px] border border-[var(--border)] bg-[var(--background)] px-4">
                      <input
                        checked={embeddingModel!.sendDimensions}
                        onChange={(event) =>
                          updateEmbeddingModel(embeddingModel!.id, {
                            sendDimensions: event.target.checked,
                          })
                        }
                        type="checkbox"
                        className="h-4 w-4 rounded"
                      />
                      <span className="text-sm">发送 dimensions 参数</span>
                    </div>
                  </label>
                  <label className="grid gap-2 text-sm text-[var(--foreground)] md:col-span-2">
                    <SectionLabel>来源</SectionLabel>
                    <textarea
                      value={embeddingModel!.source}
                      onChange={(event) =>
                        updateEmbeddingModel(embeddingModel!.id, { source: event.target.value })
                      }
                      className="min-h-[112px] rounded-[14px] border border-[var(--border)] bg-[var(--background)] px-4 py-3 text-sm outline-none transition focus:border-[var(--ring)]"
                    />
                  </label>
                </div>
              </section>
                </>
              )}
            </div>
          </>
        ) : null}

        {activeTab === "reranker" ? (
          <>
            <aside className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="text-sm font-medium text-[var(--foreground)]">
                  配置文件
                </div>
                <button
                  onClick={() =>
                    updateSettings((current) => {
                      const profile = createNewRerankerProfile();
                      return {
                        ...current,
                        rerankerProfiles: [...current.rerankerProfiles, profile],
                        activeRerankerProfileId: profile.id,
                      };
                    })
                  }
                  className="inline-flex h-9 items-center gap-1 rounded-[12px] border border-[var(--border)] px-3 text-sm"
                >
                  <Plus className="h-4 w-4" />
                  配置文件
                </button>
              </div>
              <div className="rounded-[18px] border border-[var(--border)] bg-[var(--card)] px-4 py-3">
                <div className="space-y-4">
                  {settings.rerankerProfiles.map((profile) => {
                    const active = profile.id === settings.activeRerankerProfileId;
                    const currentModel =
                      profile.models.find((model) => model.id === profile.activeModelId) ||
                      profile.models[0];
                    return (
                      <button
                        key={profile.id}
                        onClick={() =>
                          updateSettings((current) => ({
                            ...current,
                            activeRerankerProfileId: profile.id,
                          }))
                        }
                        className={`block w-full border-b border-[var(--border)] pb-4 text-left last:border-0 last:pb-0 ${
                          active ? "text-[var(--foreground)]" : "text-[var(--muted-foreground)]"
                        }`}
                      >
                        <div className="text-[17px] font-semibold tracking-tight">
                          {profile.name}
                        </div>
                        <div className="mt-1 truncate text-xs">{profile.endpointUrl}</div>
                        <div className="mt-3 text-xs">当前模型</div>
                        <div className="mt-1 text-sm font-medium">{currentModel.label}</div>
                      </button>
                    );
                  })}
                </div>
                <button
                  onClick={removeRerankerProfile}
                  className="mt-5 inline-flex items-center gap-2 text-sm text-[var(--muted-foreground)]"
                >
                  <Trash2 className="h-4 w-4" />
                  删除配置文件
                </button>
              </div>
            </aside>

            <div className="space-y-5">
              {!hasRerankerProfile ? (
                <section className="rounded-[18px] border border-dashed border-[var(--border)] bg-[var(--card)] px-5 py-8">
                  <div className="text-lg font-semibold tracking-tight">还没有 Reranker 配置</div>
                  <div className="mt-2 max-w-2xl text-sm leading-7 text-[var(--muted-foreground)]">
                    这里用于配置候选重排模型。若当前 provider 没有专用 rerank endpoint，也可以保持
                    mock 或空模型，让后端退回 LLM fallback。
                  </div>
                </section>
              ) : (
                <>
                  <section className="rounded-[18px] border border-[var(--border)] bg-[var(--card)] px-5 py-5">
                    <div className="mb-5 text-lg font-semibold tracking-tight">配置文件</div>
                    <div className="grid gap-4 md:grid-cols-2">
                      <TextField
                        label="名称"
                        value={rerankerProfile!.name}
                        onChange={(value) =>
                          updateRerankerProfile(rerankerProfile!.id, { name: value })
                        }
                      />
                      <SelectField
                        label="提供商"
                        value={rerankerProfile!.provider}
                        options={providerOptions}
                        onChange={changeRerankerProvider}
                      />
                    </div>
                    <div className="mt-4">
                      <TextField
                        label="Endpoint URL"
                        value={rerankerProfile!.endpointUrl}
                        onChange={(value) =>
                          updateRerankerProfile(rerankerProfile!.id, { endpointUrl: value })
                        }
                      />
                    </div>
                    <div className="mt-4 grid gap-4 md:grid-cols-[minmax(0,1fr)_48px]">
                      <TextField
                        label="API Key"
                        value={rerankerProfile!.apiKey}
                        type={showRerankerKey ? "text" : "password"}
                        onChange={(value) =>
                          updateRerankerProfile(rerankerProfile!.id, { apiKey: value })
                        }
                      />
                      <button
                        onClick={() => setShowRerankerKey((value) => !value)}
                        className="mt-[26px] inline-flex h-12 items-center justify-center rounded-[14px] border border-[var(--border)] bg-[var(--background)]"
                      >
                        {showRerankerKey ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                    <div className="mt-4 grid gap-4 md:grid-cols-2">
                      <TextField
                        label="API 版本"
                        value={rerankerProfile!.apiVersion}
                        placeholder="可选"
                        onChange={(value) =>
                          updateRerankerProfile(rerankerProfile!.id, { apiVersion: value })
                        }
                      />
                      <label className="grid gap-2 text-sm text-[var(--foreground)]">
                        <SectionLabel>额外请求头 (JSON)</SectionLabel>
                        <textarea
                          value={rerankerProfile!.extraHeadersText}
                          onChange={(event) =>
                            updateRerankerProfile(rerankerProfile!.id, {
                              extraHeadersText: event.target.value,
                            })
                          }
                          className="min-h-[112px] rounded-[14px] border border-[var(--border)] bg-[var(--background)] px-4 py-3 text-sm outline-none transition focus:border-[var(--ring)]"
                        />
                      </label>
                    </div>
                  </section>

                  <section className="rounded-[18px] border border-[var(--border)] bg-[var(--card)] px-5 py-5">
                    <div className="mb-4 flex items-center justify-between">
                      <div className="text-lg font-semibold tracking-tight">模型列表</div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={addRerankerModel}
                          className="inline-flex h-9 items-center gap-1 rounded-[12px] border border-[var(--border)] px-3 text-sm"
                        >
                          <Plus className="h-4 w-4" />
                          模型
                        </button>
                        <button
                          onClick={removeRerankerModel}
                          className="inline-flex h-9 items-center gap-1 rounded-[12px] text-sm text-[var(--muted-foreground)]"
                        >
                          <Trash2 className="h-4 w-4" />
                          删除
                        </button>
                      </div>
                    </div>
                    <div className="mb-4 flex flex-wrap gap-2">
                      {rerankerProfile!.models.map((model) => {
                        const active = model.id === rerankerProfile!.activeModelId;
                        return (
                          <button
                            key={model.id}
                            onClick={() =>
                              updateRerankerProfile(rerankerProfile!.id, {
                                activeModelId: model.id,
                              })
                            }
                            className={`inline-flex h-9 items-center rounded-full px-4 text-sm ${
                              active
                                ? "bg-[#1e1b18] text-white"
                                : "bg-[var(--secondary)] text-[var(--foreground)]"
                            }`}
                          >
                            <CircleDot className="mr-2 h-4 w-4" />
                            {model.label}
                          </button>
                        );
                      })}
                    </div>
                    <div className="grid gap-4 md:grid-cols-2">
                      <TextField
                        label="标签"
                        value={rerankerModel!.label}
                        onChange={(value) =>
                          updateRerankerModel(rerankerModel!.id, { label: value })
                        }
                      />
                      <TextField
                        label="模型 ID"
                        value={rerankerModel!.modelId}
                        onChange={(value) =>
                          updateRerankerModel(rerankerModel!.id, { modelId: value })
                        }
                      />
                      <label className="grid gap-2 text-sm text-[var(--foreground)] md:col-span-2">
                        <SectionLabel>来源</SectionLabel>
                        <textarea
                          value={rerankerModel!.source}
                          onChange={(event) =>
                            updateRerankerModel(rerankerModel!.id, { source: event.target.value })
                          }
                          className="min-h-[112px] rounded-[14px] border border-[var(--border)] bg-[var(--background)] px-4 py-3 text-sm outline-none transition focus:border-[var(--ring)]"
                        />
                      </label>
                    </div>
                  </section>
                </>
              )}
            </div>
          </>
        ) : null}

      </div>

      <section className="mt-6 rounded-[18px] border border-[var(--border)] bg-[var(--card)]">
        <div className="flex items-center justify-between px-5 py-4">
          <div className="inline-flex items-center gap-2 text-sm font-medium text-[var(--foreground)]">
            <ChevronDown className="h-4 w-4" />
            诊断
          </div>
          <button
            onClick={() =>
              void runDiagnostic(
                activeTab === "embedding"
                  ? "embedding"
                  : activeTab === "reranker"
                    ? "reranker"
                    : "llm",
              )
            }
            disabled={
              diagnostics.loading !== null ||
              (activeTab === "llm" && !hasLlmProfile) ||
              (activeTab === "embedding" && !hasEmbeddingProfile) ||
              (activeTab === "reranker" && !hasRerankerProfile)
            }
            className="inline-flex h-9 items-center gap-2 rounded-[12px] border border-[var(--border)] px-3 text-sm disabled:opacity-50"
          >
            运行测试
          </button>
          <button
            onClick={() => void rebuildRetrieval()}
            disabled={diagnostics.loading !== null}
            className="inline-flex h-9 items-center gap-2 rounded-[12px] border border-[var(--border)] px-3 text-sm disabled:opacity-50"
          >
            重建向量
          </button>
        </div>
        <div className="border-t border-[var(--border)] px-5 py-4">
          <div className="mb-3 text-sm text-[var(--muted-foreground)]">
            为当前
            {activeTab === "embedding"
              ? " embedding "
              : activeTab === "reranker"
                ? " reranker "
                : " llm "}
            配置生成完整请求快照、请求目标、响应摘要和服务特征验证。
          </div>
          {((activeTab === "llm" && !hasLlmProfile) ||
            (activeTab === "embedding" && !hasEmbeddingProfile) ||
            (activeTab === "reranker" && !hasRerankerProfile)) && (
            <div className="mb-3 rounded-[14px] border border-[var(--border)] bg-[var(--background)] px-4 py-3 text-sm text-[var(--muted-foreground)]">
              先创建并填写当前标签页的配置文件，诊断区才会开始发送真实测试请求。
            </div>
          )}
          {runtimeError || lastError ? (
            <div className="mb-3 flex items-start justify-between gap-3 rounded-[14px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              <span>{runtimeError || lastError}</span>
              <button onClick={clearLastError} className="shrink-0 text-xs">
                关闭
              </button>
            </div>
          ) : null}
          <DiagnosticsConsole
            result={
              activeTab === "embedding"
                ? diagnostics.embedding
                : activeTab === "reranker"
                  ? diagnostics.reranker
                  : diagnostics.llm
            }
          />
        </div>
      </section>
    </div>
  );
}
