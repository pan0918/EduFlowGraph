export interface EventRecord {
  event_id: string;
  stream_index?: number;
  session_id: string;
  turn_index: number;
  timestamp: string;
  segment_id?: string | null;
  actor: string;
  event_type: string;
  content: string;
  metadata?: Record<string, unknown>;
  causation_id?: string | null;
  correlation_id?: string | null;
}

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
  provenance: {
    segment_id: string;
    session_id: string;
    source_event_ids: string[];
    start_time: string;
    end_time: string;
  };
  summary: {
    title: string;
    topic_summary: string;
    short_summary: string;
  };
  learner_problem: {
    student_question: string;
    detected_problem: string;
    misconceptions: string[];
    understanding_before: string;
    difficulty_signals: string[];
  };
  tutor_action?: {
    main_strategy?: string;
    strategy_summary?: string;
    teaching_steps?: string[];
    used_examples?: boolean;
    used_assessment?: boolean;
  };
  learning_outcome?: {
    result?: string;
    understanding_after?: string;
    score?: number;
    evidence?: string;
    needs_follow_up?: boolean;
    follow_up_suggestion?: string;
  };
  retrieval?: {
    keywords: string[];
    embedding_text: string;
    embedding_vector?: number[];
    embedding_metadata?: RetrievalEmbeddingMetadata;
  };
  extraction_metadata?: {
    extractor_version?: string;
    boundary_reason?: string;
    boundary_confidence?: number;
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
  events: EventRecord[];
  concepts: ConceptNode[];
  episodes: EpisodeNode[];
  skills: SkillNode[];
  edges: GraphEdge[];
  boundary_segments?: BoundarySegment[];
  retrieval_health?: {
    total_nodes: number;
    valid_vectors: number;
    stale_vectors: number;
  };
}

export interface BoundaryDecision {
  should_end: boolean;
  should_wait: boolean;
  force_end: boolean;
  confidence: number;
  reason: string;
  completion_status: string;
  topic_summary: string;
}

export interface BoundarySegment {
  session_id: string;
  decision: BoundaryDecision;
  events: EventRecord[];
}

export interface RetrievedContext {
  concepts: ConceptNode[];
  episodes: EpisodeNode[];
  skills: SkillNode[];
  retrieval_summary?: {
    stale_vectors?: number;
    concept_hits?: number;
    episode_hits?: number;
    skill_hits?: number;
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
