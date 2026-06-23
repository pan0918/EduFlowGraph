import type { RetrievedContext } from "@/lib/types";

export interface UsageSummary {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  cachedTokens: number;
  cacheHitRate: number;
}

export interface ReasoningPanelText {
  content: string;
  truncated: boolean;
  originalLength: number;
}

export interface RetrievalTraceSummary {
  conceptCount: number;
  episodeCount: number;
  skillCount: number;
  profileCount: number;
  totalCount: number;
  hasContext: boolean;
  staleVectors: number;
  conceptHits: number;
  episodeHits: number;
  skillHits: number;
  profileHits: number;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asNumber(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

export function summarizeUsage(usage?: Record<string, unknown>): UsageSummary | null {
  if (!usage) return null;
  const promptDetails = asRecord(usage.prompt_tokens_details);
  const inputDetails = asRecord(usage.input_tokens_details);
  const promptCacheHitTokens = asNumber(usage.prompt_cache_hit_tokens);
  const promptCacheMissTokens = asNumber(usage.prompt_cache_miss_tokens);
  const cacheCreationInputTokens = asNumber(usage.cache_creation_input_tokens);
  const cacheReadInputTokens = asNumber(usage.cache_read_input_tokens);
  const promptCacheBreakdownTokens = promptCacheHitTokens + promptCacheMissTokens;
  const anthropicPromptTokens =
    cacheReadInputTokens || cacheCreationInputTokens
      ? asNumber(usage.input_tokens) + cacheCreationInputTokens + cacheReadInputTokens
      : 0;
  const promptTokens =
    asNumber(usage.prompt_tokens) ||
    anthropicPromptTokens ||
    asNumber(usage.input_tokens) ||
    promptCacheBreakdownTokens;
  const completionTokens =
    asNumber(usage.completion_tokens) || asNumber(usage.output_tokens);
  const totalTokens =
    asNumber(usage.total_tokens) || promptTokens + completionTokens;
  const cachedTokens =
    asNumber(promptDetails.cached_tokens) ||
    asNumber(inputDetails.cached_tokens) ||
    asNumber(inputDetails.cache_read) ||
    asNumber(usage.cached_tokens) ||
    promptCacheHitTokens ||
    cacheReadInputTokens;
  const cacheHitRate =
    promptTokens > 0 ? Math.min(1, Math.max(0, cachedTokens / promptTokens)) : 0;

  if (!promptTokens && !completionTokens && !totalTokens && !cachedTokens) {
    return null;
  }

  return {
    promptTokens,
    completionTokens,
    totalTokens,
    cachedTokens,
    cacheHitRate,
  };
}

export function summarizeRetrieval(
  retrieval?: RetrievedContext | null,
): RetrievalTraceSummary | null {
  if (!retrieval) return null;
  const conceptCount = retrieval.concepts.length;
  const episodeCount = retrieval.episodes.length;
  const skillCount = retrieval.skills.length;
  const profileModels = retrieval.profile?.models;
  const profileCount = profileModels
    ? (["learner_model", "strategy_model", "context_model"] as const).filter(
        (m) => profileModels[m]?.summary?.trim(),
      ).length
    : 0;
  const retrievalSummary = retrieval.retrieval_summary;

  return {
    conceptCount,
    episodeCount,
    skillCount,
    profileCount,
    totalCount: conceptCount + episodeCount + skillCount + profileCount,
    hasContext: true,
    staleVectors: asNumber(retrievalSummary?.stale_vectors),
    conceptHits: asNumber(retrievalSummary?.concept_hits),
    episodeHits: asNumber(retrievalSummary?.episode_hits),
    skillHits: asNumber(retrievalSummary?.skill_hits),
    profileHits: asNumber(retrievalSummary?.profile_hits),
  };
}

export function formatReasoningForPanel(
  reasoning?: string,
  maxChars = 6000,
): ReasoningPanelText {
  const content = reasoning || "";
  if (content.length <= maxChars) {
    return {
      content,
      truncated: false,
      originalLength: content.length,
    };
  }

  const edgeLength = Math.max(1, Math.floor(maxChars / 2));
  const omitted = content.length - edgeLength * 2;
  return {
    content: `${content.slice(0, edgeLength)}\n\n... 已省略中间 ${omitted.toLocaleString()} 个字符，以保持界面流畅 ...\n\n${content.slice(-edgeLength)}`,
    truncated: true,
    originalLength: content.length,
  };
}
