import type {
  EmbeddingModelEntry,
  EmbeddingProfile,
  LLMModelEntry,
  LLMProfile,
  RerankerModelEntry,
  RerankerProfile,
  RuntimeConfig,
  WorkspaceSettings,
} from "@/lib/types";

export type ProviderId = "openai" | "deepseek" | "siliconflow" | "mock";

export interface ProviderOption {
  id: ProviderId;
  label: string;
  llmBaseUrl: string;
  embeddingEndpointUrl: string;
  rerankerEndpointUrl: string;
}

export const PROVIDER_OPTIONS: ProviderOption[] = [
  {
    id: "openai",
    label: "OpenAI",
    llmBaseUrl: "https://api.openai.com/v1",
    embeddingEndpointUrl: "https://api.openai.com/v1/embeddings",
    rerankerEndpointUrl: "https://api.openai.com/v1/rerank",
  },
  {
    id: "deepseek",
    label: "DeepSeek",
    llmBaseUrl: "https://api.deepseek.com",
    embeddingEndpointUrl: "https://api.deepseek.com/embeddings",
    rerankerEndpointUrl: "https://api.deepseek.com/rerank",
  },
  {
    id: "siliconflow",
    label: "SiliconFlow",
    llmBaseUrl: "https://api.siliconflow.cn/v1",
    embeddingEndpointUrl: "https://api.siliconflow.cn/v1/embeddings",
    rerankerEndpointUrl: "https://api.siliconflow.cn/v1/rerank",
  },
  {
    id: "mock",
    label: "Mock",
    llmBaseUrl: "",
    embeddingEndpointUrl: "",
    rerankerEndpointUrl: "",
  },
];

function coerceProviderId(value: string | undefined | null): ProviderId {
  const normalized = String(value || "").trim().toLowerCase();
  if (
    normalized === "openai" ||
    normalized === "openai-compatible" ||
    normalized === "openai_compatible"
  ) {
    return "openai";
  }
  if (normalized === "deepseek") {
    return "deepseek";
  }
  if (normalized === "siliconflow" || normalized === "silicon-flow") {
    return "siliconflow";
  }
  if (normalized === "mock") {
    return "mock";
  }
  return "openai";
}

export function getProviderOption(providerId: string | undefined | null): ProviderOption {
  const id = coerceProviderId(providerId);
  return PROVIDER_OPTIONS.find((item) => item.id === id) || PROVIDER_OPTIONS[0];
}

function parseExtraHeadersText(text: string): Record<string, string> {
  const trimmed = text.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("额外请求头必须是 JSON 对象。");
  }
  return Object.fromEntries(
    Object.entries(parsed).map(([key, value]) => [String(key), String(value)]),
  );
}

function createLlmModel(id: string, label: string, modelId: string, contextWindow: number, source: string): LLMModelEntry {
  return { id, label, modelId, contextWindow, source };
}

function createEmbeddingModel(
  id: string,
  label: string,
  modelId: string,
  dimensions: number,
  sendDimensions: boolean,
  source: string,
): EmbeddingModelEntry {
  return { id, label, modelId, dimensions, sendDimensions, source };
}

function createRerankerModel(
  id: string,
  label: string,
  modelId: string,
  source: string,
): RerankerModelEntry {
  return { id, label, modelId, source };
}

function createLlmProfile(
  id: string,
  name: string,
  provider: string,
  baseUrl: string,
  model: LLMModelEntry,
): LLMProfile {
  return {
    id,
    name,
    provider,
    baseUrl,
    apiKey: "",
    apiVersion: "",
    extraHeadersText: "{}",
    models: [model],
    activeModelId: model.id,
  };
}

function createEmbeddingProfile(
  id: string,
  name: string,
  provider: string,
  endpointUrl: string,
  model: EmbeddingModelEntry,
): EmbeddingProfile {
  return {
    id,
    name,
    provider,
    endpointUrl,
    apiKey: "",
    apiVersion: "",
    extraHeadersText: "{}",
    models: [model],
    activeModelId: model.id,
  };
}

function createRerankerProfile(
  id: string,
  name: string,
  provider: string,
  endpointUrl: string,
  model: RerankerModelEntry,
): RerankerProfile {
  return {
    id,
    name,
    provider,
    endpointUrl,
    apiKey: "",
    apiVersion: "",
    extraHeadersText: "{}",
    models: [model],
    activeModelId: model.id,
  };
}

export const DEFAULT_SETTINGS: WorkspaceSettings = {
  sessionId: "session_demo",
  extractionTurns: 4,
  memoryMode: "ordinary",
  llmProfiles: [],
  activeLlmProfileId: "",
  embeddingProfiles: [],
  activeEmbeddingProfileId: "",
  rerankerProfiles: [],
  activeRerankerProfileId: "",
};

function ensureLlmProfile(profile: LLMProfile): LLMProfile {
  const models = profile.models.length
    ? profile.models
    : [
        createLlmModel(
          `${profile.id}-model-default`,
          profile.name || "default-model",
          profile.name || "default-model",
          65536,
          "手动创建的模型配置。",
        ),
      ];
  const activeModelId = models.some((item) => item.id === profile.activeModelId)
    ? profile.activeModelId
    : models[0].id;
  return {
    ...profile,
    name: profile.name || "未命名对话配置",
    provider: coerceProviderId(profile.provider),
    extraHeadersText: profile.extraHeadersText || "{}",
    models,
    activeModelId,
  };
}

function ensureEmbeddingProfile(profile: EmbeddingProfile): EmbeddingProfile {
  const models = profile.models.length
    ? profile.models
    : [
        createEmbeddingModel(
          `${profile.id}-model-default`,
          profile.name || "default-embedding",
          profile.name || "default-embedding",
          1024,
          false,
          "手动创建的向量模型配置。",
        ),
      ];
  const activeModelId = models.some((item) => item.id === profile.activeModelId)
    ? profile.activeModelId
    : models[0].id;
  return {
    ...profile,
    name: profile.name || "未命名向量配置",
    provider: coerceProviderId(profile.provider),
    extraHeadersText: profile.extraHeadersText || "{}",
    models,
    activeModelId,
  };
}

function ensureRerankerProfile(profile: RerankerProfile): RerankerProfile {
  const models = profile.models.length
    ? profile.models
    : [
        createRerankerModel(
          `${profile.id}-model-default`,
          profile.name || "default-reranker",
          profile.name || "default-reranker",
          "手动创建的重排模型配置。",
        ),
      ];
  const activeModelId = models.some((item) => item.id === profile.activeModelId)
    ? profile.activeModelId
    : models[0].id;
  return {
    ...profile,
    name: profile.name || "未命名重排配置",
    provider: coerceProviderId(profile.provider),
    extraHeadersText: profile.extraHeadersText || "{}",
    models,
    activeModelId,
  };
}

export function normalizeSettings(input: unknown): WorkspaceSettings {
  const raw = (input && typeof input === "object" ? input : {}) as Partial<WorkspaceSettings> &
    Record<string, unknown>;

  if ("provider" in raw || "chatModel" in raw || "embeddingModel" in raw) {
    const legacyProvider = coerceProviderId(String(raw.provider || "mock"));
    const legacyBaseUrl = String(raw.baseUrl || "https://api.openai.com/v1");
    const legacyChatModel = String(raw.chatModel || "gpt-4o-mini");
    const legacyEmbeddingModel = String(raw.embeddingModel || "text-embedding-3-small");
    const legacyApiKey = String(raw.apiKey || "");

    return {
      ...DEFAULT_SETTINGS,
      sessionId: String(raw.sessionId || DEFAULT_SETTINGS.sessionId),
      extractionTurns: Number(raw.extractionTurns || DEFAULT_SETTINGS.extractionTurns),
      memoryMode:
        raw.memoryMode === "memory_augmented" ? "memory_augmented" : "ordinary",
      llmProfiles: [
        {
          id: "llm-legacy",
          name: "默认对话配置",
          provider: legacyProvider,
          baseUrl: legacyBaseUrl,
          apiKey: legacyApiKey,
          apiVersion: "",
          extraHeadersText: "{}",
          models: [
            createLlmModel(
              "llm-model-legacy",
              legacyChatModel,
              legacyChatModel,
              65536,
              "从旧版本地配置迁移而来。",
            ),
          ],
          activeModelId: "llm-model-legacy",
        },
      ],
      activeLlmProfileId: "llm-legacy",
      embeddingProfiles: [
        {
          id: "embedding-legacy",
          name: "默认向量配置",
          provider: legacyProvider,
          endpointUrl: legacyBaseUrl.replace(/\/$/, "") + "/embeddings",
          apiKey: legacyApiKey,
          apiVersion: "",
          extraHeadersText: "{}",
          models: [
            createEmbeddingModel(
              "embedding-model-legacy",
              legacyEmbeddingModel,
              legacyEmbeddingModel,
              1024,
              false,
              "从旧版本地配置迁移而来。",
            ),
          ],
          activeModelId: "embedding-model-legacy",
        },
      ],
      activeEmbeddingProfileId: "embedding-legacy",
      rerankerProfiles: [
        {
          id: "reranker-legacy",
          name: "默认重排配置",
          provider: "mock",
          endpointUrl: "",
          apiKey: "",
          apiVersion: "",
          extraHeadersText: "{}",
          models: [createRerankerModel("reranker-model-legacy", "LLM fallback", "", "从旧版本地配置迁移而来。")],
          activeModelId: "reranker-model-legacy",
        },
      ],
      activeRerankerProfileId: "reranker-legacy",
    };
  }

  const llmProfiles = Array.isArray(raw.llmProfiles)
    ? raw.llmProfiles.map((profile) => ensureLlmProfile(profile as LLMProfile))
    : DEFAULT_SETTINGS.llmProfiles;
  const embeddingProfiles = Array.isArray(raw.embeddingProfiles)
    ? raw.embeddingProfiles.map((profile) => ensureEmbeddingProfile(profile as EmbeddingProfile))
    : DEFAULT_SETTINGS.embeddingProfiles;
  const rerankerProfiles = Array.isArray(raw.rerankerProfiles)
    ? raw.rerankerProfiles.map((profile) => ensureRerankerProfile(profile as RerankerProfile))
    : DEFAULT_SETTINGS.rerankerProfiles;
  const normalizedRerankerProfiles =
    rerankerProfiles.length > 0
      ? rerankerProfiles
      : [createNewRerankerProfile()];
  return {
    sessionId: String(raw.sessionId || DEFAULT_SETTINGS.sessionId),
    extractionTurns: Number(raw.extractionTurns || DEFAULT_SETTINGS.extractionTurns),
    memoryMode: raw.memoryMode === "memory_augmented" ? "memory_augmented" : "ordinary",
    llmProfiles,
    activeLlmProfileId:
      llmProfiles.find((profile) => profile.id === raw.activeLlmProfileId)?.id ||
      llmProfiles[0]?.id ||
      "",
    embeddingProfiles,
    activeEmbeddingProfileId:
      embeddingProfiles.find((profile) => profile.id === raw.activeEmbeddingProfileId)?.id ||
      embeddingProfiles[0]?.id ||
      "",
    rerankerProfiles: normalizedRerankerProfiles,
    activeRerankerProfileId:
      normalizedRerankerProfiles.find(
        (profile) => profile.id === raw.activeRerankerProfileId,
      )?.id ||
      normalizedRerankerProfiles[0]?.id ||
      "",
  };
}

export function getActiveLlmProfile(settings: WorkspaceSettings): LLMProfile | null {
  return (
    settings.llmProfiles.find((profile) => profile.id === settings.activeLlmProfileId) ||
    settings.llmProfiles[0] ||
    null
  );
}

export function getActiveLlmModel(settings: WorkspaceSettings): LLMModelEntry | null {
  const profile = getActiveLlmProfile(settings);
  if (!profile) return null;
  return profile.models.find((item) => item.id === profile.activeModelId) || profile.models[0] || null;
}

export function getActiveEmbeddingProfile(settings: WorkspaceSettings): EmbeddingProfile | null {
  return (
    settings.embeddingProfiles.find((profile) => profile.id === settings.activeEmbeddingProfileId) ||
    settings.embeddingProfiles[0] ||
    null
  );
}

export function getActiveEmbeddingModel(settings: WorkspaceSettings): EmbeddingModelEntry | null {
  const profile = getActiveEmbeddingProfile(settings);
  if (!profile) return null;
  return profile.models.find((item) => item.id === profile.activeModelId) || profile.models[0] || null;
}

export function getActiveRerankerProfile(settings: WorkspaceSettings): RerankerProfile | null {
  return (
    settings.rerankerProfiles.find(
      (profile) => profile.id === settings.activeRerankerProfileId,
    ) ||
    settings.rerankerProfiles[0] ||
    null
  );
}

export function getActiveRerankerModel(settings: WorkspaceSettings): RerankerModelEntry | null {
  const profile = getActiveRerankerProfile(settings);
  if (!profile) return null;
  return profile.models.find((item) => item.id === profile.activeModelId) || profile.models[0] || null;
}

export function buildRuntimeConfig(settings: WorkspaceSettings): RuntimeConfig {
  const llmProfile = getActiveLlmProfile(settings);
  const llmModel = getActiveLlmModel(settings);
  const embeddingProfile = getActiveEmbeddingProfile(settings);
  const embeddingModel = getActiveEmbeddingModel(settings);
  const rerankerProfile = getActiveRerankerProfile(settings);
  const rerankerModel = getActiveRerankerModel(settings);
  if (!llmProfile || !llmModel) {
    throw new Error("请先在设置页创建并完成 LLM 配置。");
  }
  if (!embeddingProfile || !embeddingModel) {
    throw new Error("请先在设置页创建并完成 Embedding 配置。");
  }
  if (!rerankerProfile || !rerankerModel) {
    throw new Error("请先在设置页创建并完成 Reranker 配置。");
  }

  return {
    llm: {
      provider: coerceProviderId(llmProfile.provider),
      name: llmProfile.name,
      base_url: llmProfile.baseUrl,
      api_key: llmProfile.apiKey,
      api_version: llmProfile.apiVersion,
      extra_headers: parseExtraHeadersText(llmProfile.extraHeadersText),
      model_id: llmModel.modelId,
      model_label: llmModel.label,
      context_window: llmModel.contextWindow || null,
    },
    embedding: {
      provider: coerceProviderId(embeddingProfile.provider),
      name: embeddingProfile.name,
      endpoint_url: embeddingProfile.endpointUrl,
      api_key: embeddingProfile.apiKey,
      api_version: embeddingProfile.apiVersion,
      extra_headers: parseExtraHeadersText(embeddingProfile.extraHeadersText),
      model_id: embeddingModel.modelId,
      model_label: embeddingModel.label,
      dimensions: embeddingModel.dimensions || null,
      send_dimensions: embeddingModel.sendDimensions,
    },
    reranker: {
      provider: coerceProviderId(rerankerProfile.provider),
      name: rerankerProfile.name,
      endpoint_url: rerankerProfile.endpointUrl,
      api_key: rerankerProfile.apiKey,
      api_version: rerankerProfile.apiVersion,
      extra_headers: parseExtraHeadersText(rerankerProfile.extraHeadersText),
      model_id: rerankerModel.modelId,
      model_label: rerankerModel.label,
    },
  };
}

export function createNewLlmProfile(): LLMProfile {
  const id = `llm-${crypto.randomUUID()}`;
  const preset = getProviderOption("openai");
  const model = createLlmModel(
    `${id}-model`,
    "",
    "",
    0,
    "",
  );
  return createLlmProfile(
    id,
    "未命名对话配置",
    preset.id,
    preset.llmBaseUrl,
    model,
  );
}

export function createNewEmbeddingProfile(): EmbeddingProfile {
  const id = `embedding-${crypto.randomUUID()}`;
  const preset = getProviderOption("openai");
  const model = createEmbeddingModel(
    `${id}-model`,
    "",
    "",
    0,
    false,
    "",
  );
  return createEmbeddingProfile(
    id,
    "未命名向量配置",
    preset.id,
    preset.embeddingEndpointUrl,
    model,
  );
}

export function createNewRerankerProfile(): RerankerProfile {
  const id = `reranker-${crypto.randomUUID()}`;
  const preset = getProviderOption("mock");
  const model = createRerankerModel(`${id}-model`, "LLM fallback", "", "");
  return createRerankerProfile(
    id,
    "未命名重排配置",
    preset.id,
    preset.rerankerEndpointUrl,
    model,
  );
}

export function createNewLlmModel(): LLMModelEntry {
  const id = `llm-model-${crypto.randomUUID()}`;
  return createLlmModel(id, "", "", 0, "");
}

export function createNewEmbeddingModel(): EmbeddingModelEntry {
  const id = `embedding-model-${crypto.randomUUID()}`;
  return createEmbeddingModel(
    id,
    "",
    "",
    0,
    false,
    "",
  );
}

export function createNewRerankerModel(): RerankerModelEntry {
  const id = `reranker-model-${crypto.randomUUID()}`;
  return createRerankerModel(id, "", "", "");
}
