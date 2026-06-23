export interface ConceptNode {
  concept_id: string;
  node_id: string;
  node_type: "concept";
  name: string;
  description?: string;
  aliases?: string[];
  retrieval?: RetrievalAsset;
  metadata?: {
    created_at?: string;
    updated_at?: string;
  };
}

export interface EpisodeNode {
  episode_id: string;
  node_id: string;
  node_type: "episode";
  episode_type: string;
  title: string;
  summary: string;
  memory_value: string;
  provenance: {
    session_id: string;
    turn_range: [number, number];
    start_time: string;
    end_time: string;
  };
  learner: {
    goal: string;
    obstacle: string;
    initial_state: string;
    evidence: string[];
  };
  tutor: {
    strategy: string;
    key_moves: string[];
  };
  outcome: {
    status: string;
    evidence: string;
    next_step: string;
  };
  retrieval?: {
    keywords: string[];
    embedding_text: string;
    embedding_vector?: number[];
    embedding_metadata?: RetrievalEmbeddingMetadata;
  };
  extraction_metadata?: {
    extractor_version?: string;
    extraction_confidence?: number;
    created_at?: string;
  };
}

export interface SkillNode {
  skill_id: string;
  node_id: string;
  node_type: "skill";
  name: string;
  status: "candidate" | "active";
  trigger: string;
  concept_scope?: string[];
  difficulty_pattern: string;
  teaching_actions?: string[];
  procedure?: string[];
  success_criteria?: string[];
  retrieval?: RetrievalAsset;
  quality?: {
    support_episode_count?: number;
    validation_success_count?: number;
    validation_fail_count?: number;
    confidence?: number;
    last_validated_at?: string | null;
  };
  metadata?: {
    created_at?: string;
    updated_at?: string;
    extractor_version?: string;
    source_episode_ids?: string[];
    evidence_concept_scope?: string[];
  };
}

export type ProfileModelName = "learner_model" | "strategy_model" | "context_model";

export interface ProfileModelEntry {
  summary: string;
  updated_at?: string | null;
  revisions: number;
}

export interface ProfileChange {
  at?: string | null;
  model: ProfileModelName;
  note: string;
}

export interface LearnerProfileSnapshot {
  models: {
    learner_model: ProfileModelEntry;
    strategy_model: ProfileModelEntry;
    context_model: ProfileModelEntry;
  };
  recent_changes: ProfileChange[];
  updated_at?: string | null;
  revision_count: number;
  health: {
    status: string;
    message?: string;
  };
}

export interface RetrievalEmbeddingMetadata {
  provider?: string;
  model_id?: string;
  dimensions?: number;
  created_at?: string;
}

export interface RetrievalAsset {
  keywords: string[];
  embedding_text: string;
  embedding_vector?: number[];
  embedding_metadata?: RetrievalEmbeddingMetadata;
}

export interface GraphEdge {
  edge_id: string;
  edge_type: string;
  source: string;
  target: string;
  weight?: number;
  evidence?: string;
  metadata?: {
    structural_role?: "main" | "supporting" | "mentioned";
    learner_relation?: "confused" | "clarified" | "neutral";
    role?: "source_evidence" | "validation";
    confidence?: number;
    extractor_version?: string;
    created_at?: string;
    [key: string]: unknown;
  };
}

export interface DashboardSnapshot {
  concepts: ConceptNode[];
  episodes: EpisodeNode[];
  skills: SkillNode[];
  edges: GraphEdge[];
  profile: LearnerProfileSnapshot;
  memory_flow_count: number;
  retrieval_health?: {
    total_nodes: number;
    valid_vectors: number;
    stale_vectors: number;
  };
  storage_health?: {
    backend: "sqlite" | "json" | string;
    status?: "ok" | "error" | string;
    message?: string;
    schema_version?: number;
    journal_mode?: string;
    database_size_bytes?: number;
    wal_size_bytes?: number;
    integrity?: string;
  };
}

export interface RetrievedContext {
  concepts: ConceptNode[];
  episodes: EpisodeNode[];
  skills: SkillNode[];
  profile?: LearnerProfileSnapshot;
  profile_context?: string;
  retrieval_summary?: {
    stale_vectors?: number;
    concept_hits?: number;
    episode_hits?: number;
    skill_hits?: number;
    profile_hits?: number;
    profile_anchor_hits?: number;
    profile_fusion?: Record<string, unknown>;
    embedding_error?: string | null;
    query_info?: Record<string, unknown>;
    top_matches?: {
      concepts?: Array<Record<string, unknown>>;
      episodes?: Array<Record<string, unknown>>;
      skills?: Array<Record<string, unknown>>;
    };
  };
  memory_context_pack?: string;
}

export interface LLMModelEntry {
  id: string;
  label: string;
  modelId: string;
  contextWindow: number;
  source: string;
}

export interface EmbeddingModelEntry {
  id: string;
  label: string;
  modelId: string;
  dimensions: number;
  sendDimensions: boolean;
  source: string;
}

export interface LLMProfile {
  id: string;
  name: string;
  provider: string;
  baseUrl: string;
  apiKey: string;
  apiVersion: string;
  extraHeadersText: string;
  models: LLMModelEntry[];
  activeModelId: string;
}

export interface EmbeddingProfile {
  id: string;
  name: string;
  provider: string;
  endpointUrl: string;
  apiKey: string;
  apiVersion: string;
  extraHeadersText: string;
  models: EmbeddingModelEntry[];
  activeModelId: string;
}

export interface RerankerModelEntry {
  id: string;
  label: string;
  modelId: string;
  source: string;
}

export interface RerankerProfile {
  id: string;
  name: string;
  provider: string;
  endpointUrl: string;
  apiKey: string;
  apiVersion: string;
  extraHeadersText: string;
  models: RerankerModelEntry[];
  activeModelId: string;
}

export interface WorkspaceSettings {
  sessionId: string;
  extractionTurns: number;
  memoryMode: "ordinary" | "memory_augmented";
  llmProfiles: LLMProfile[];
  activeLlmProfileId: string;
  embeddingProfiles: EmbeddingProfile[];
  activeEmbeddingProfileId: string;
  rerankerProfiles: RerankerProfile[];
  activeRerankerProfileId: string;
}

export interface RuntimeLLMConfig {
  provider: string;
  name: string;
  base_url: string;
  api_key: string;
  api_version: string;
  extra_headers: Record<string, string>;
  model_id: string;
  model_label: string;
  context_window: number | null;
}

export interface RuntimeEmbeddingConfig {
  provider: string;
  name: string;
  endpoint_url: string;
  api_key: string;
  api_version: string;
  extra_headers: Record<string, string>;
  model_id: string;
  model_label: string;
  dimensions: number | null;
  send_dimensions: boolean;
}

export interface RuntimeConfig {
  llm: RuntimeLLMConfig;
  embedding: RuntimeEmbeddingConfig;
  reranker: RuntimeRerankerConfig;
}

export interface RuntimeRerankerConfig {
  provider: string;
  name: string;
  endpoint_url: string;
  api_key: string;
  api_version: string;
  extra_headers: Record<string, string>;
  model_id: string;
  model_label: string;
}

export interface DiagnosticResult {
  status: "ok" | "error";
  kind: "llm" | "embedding" | "reranker";
  provider: string;
  profile_name: string;
  model_id: string;
  latency_ms?: number;
  live_enabled?: boolean;
  request_preview?: {
    url: string;
    headers: Record<string, string>;
    payload: Record<string, unknown>;
  };
  contract_summary?: Record<string, unknown>;
  response_preview?: string;
  error?: string;
}
