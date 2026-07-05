import type { AccessReference, AccessSummary } from './datasetAccess'

export interface SynonymAlias {
  term: string
  source: string
  category: string
  safe_for_retrieval: boolean
  requires_context: boolean
}

export interface EvidenceSnippet {
  field: string
  text: string
  matched_concepts?: string[]
}

export interface ConceptMapping {
  slot: string
  query_term: string
  curie: string
  label: string
  ontology: string
  iri?: string | null
  synonyms?: string[]
  match_type?: string
  source?: string
  confidence?: number
  explanation?: string
  selection_reason?: string
}

export interface InterpretedQuery {
  disease?: string | null
  tissue?: string | null
  assay?: string | null
  organism?: string | null
}

export interface ScoreBreakdown {
  evidence_score?: number
  display_rank_score?: number
  match_tier?: number
  rank_tier?: number
  match_status?: string
  [key: string]: unknown
}

/** Repository-agnostic dataset record; extended with optional access discovery fields. */
export interface DatasetCandidate {
  repository: string
  accession: string
  title: string
  description?: string
  sample_count?: number | null
  url?: string
  requested_concepts?: ConceptMapping[]
  matched_concepts?: ConceptMapping[]
  observed_assay?: string | null
  observed_organism?: string | null
  observed_disease?: string | null
  observed_tissue?: string | null
  evidence_snippets?: EvidenceSnippet[]
  score: number
  match_status?: string
  retrieval_strategy?: string | null
  retrieval_search_term?: string | null
  why_matched?: string[]
  why_partial?: string[]
  metadata_warnings?: string[]
  score_breakdown?: ScoreBreakdown | null
  /** Populated by access discovery (GEO, Expression Atlas, …). */
  access_summary?: AccessSummary | null
  /** Discovered file/page references; empty until backend discovery runs. */
  access_references?: AccessReference[]
  /** Client-side manifest selection; not part of API responses. */
  manifest_selected?: boolean
}

export interface DatasetSearchResult {
  query?: string
  interpreted_query?: InterpretedQuery
  concept_mappings?: ConceptMapping[]
  candidates?: DatasetCandidate[]
  total_found?: number
  primary_total_found?: number | null
  max_results?: number | null
  source?: string
  repository?: string
  search_term?: string | null
  search_strategies?: Array<Record<string, string | number>>
  has_more?: boolean
  retrieved_count?: number
  load_more_cursor?: unknown
  agent_context?: {
    markdown?: string
    json?: unknown
  }
}
