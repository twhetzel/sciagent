"""Pydantic models for ontology-grounded dataset discovery."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SynonymAlias(BaseModel):
    """Metadata for one ontology label, synonym, or acronym."""

    term: str
    source: str
    category: str = Field(
        ...,
        description=(
            "preferred_label, exact_synonym, dataset_phrase, broad_synonym, "
            "related_synonym, acronym, or abbreviation"
        ),
    )
    safe_for_retrieval: bool = Field(
        ...,
        description="Whether the term may be used in broad repository search",
    )
    requires_context: bool = Field(
        ...,
        description="Whether evidence matching requires nearby supporting terms",
    )


class SlotEvidenceBreakdown(BaseModel):
    """Per-facet evidence audit for ranking."""

    present: bool = False
    fields: list[str] = Field(default_factory=list)
    matched_terms: list[str] = Field(default_factory=list)


class TissueEvidenceBreakdown(SlotEvidenceBreakdown):
    """Tissue evidence with direct vs model-derived vs ambiguous classification."""

    evidence_type: str = Field(
        default="absent",
        description="direct, derived_model, ambiguous, or absent",
    )


class OrganismEvidenceBreakdown(SlotEvidenceBreakdown):
    """Organism evidence with structured taxon vs narrative metadata classification."""

    evidence_source: str = Field(
        default="absent",
        description="structured, narrative, or absent",
    )


class ScoreBreakdown(BaseModel):
    """Developer/debug audit of how a candidate was scored and matched."""

    disease: SlotEvidenceBreakdown = Field(default_factory=SlotEvidenceBreakdown)
    tissue: TissueEvidenceBreakdown = Field(default_factory=TissueEvidenceBreakdown)
    assay: SlotEvidenceBreakdown = Field(default_factory=SlotEvidenceBreakdown)
    organism: OrganismEvidenceBreakdown = Field(default_factory=OrganismEvidenceBreakdown)
    warnings: list[str] = Field(default_factory=list)
    evidence_conflicts: list[str] = Field(default_factory=list)
    warnings_count: int = 0
    evidence_conflicts_count: int = 0
    retrieval_strategy: str | None = None
    evidence_coverage: float = 0.0
    base_score: float = 0.0
    quality_adjustment: float = 0.0
    evidence_score: float = 0.0
    rank_tier: float = 0.0
    match_tier: float = 0.0
    partial_assay_subtype: str | None = None
    display_rank_score: float = 0.0
    match_tier_note: str = ""
    requested_assay: str | None = None
    observed_assay: str | None = None
    assay_mismatch: bool = False
    assay_mismatch_note: str = ""
    assay_rank_adjustment: float = 0.0
    match_status: str = "partial"


class EvidenceSnippet(BaseModel):
    """Text excerpt from a dataset record that supports a match."""

    field: str = Field(..., description="Source field, e.g. title or summary")
    text: str = Field(..., description="Excerpt text")
    matched_concepts: list[str] = Field(
        default_factory=list,
        description="Grounded concept labels found in this snippet",
    )


class ConceptMapping(BaseModel):
    """Grounded ontology concept for a query slot."""

    slot: str = Field(..., description="Query slot: disease, tissue, assay, or organism")
    query_term: str = Field(..., description="Term extracted from the user query")
    curie: str = Field(..., description="Ontology CURIE, e.g. MONDO:0005101")
    label: str = Field(..., description="Preferred ontology label")
    ontology: str = Field(..., description="Ontology prefix, e.g. MONDO")
    iri: str | None = Field(default=None, description="Ontology term IRI when available")
    synonyms: list[str] = Field(default_factory=list, description="Search synonyms")
    synonym_scopes: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Normalized synonym text to ontology scope "
            "(label, exact, broad, related, dataset) from OLS/BioPortal/curated"
        ),
    )
    aliases: list[SynonymAlias] = Field(
        default_factory=list,
        description="Classified synonym metadata for retrieval and evidence",
    )
    match_type: str = Field(default="unknown", description="How the concept was matched")
    source: str = Field(default="unknown", description="Grounding provider that produced the match")
    confidence: float = Field(default=0.0, description="Relative confidence in the grounding")
    explanation: str = Field(default="", description="Human-readable grounding rationale")
    selection_reason: str = Field(
        default="",
        description="Why this concept was chosen over alternatives (facet ontology priority)",
    )
    rejected_candidates: list[dict[str, str | float | int]] = Field(
        default_factory=list,
        description="Non-selected grounding candidates with ontology tier and provider metadata",
    )


class InterpretedQuery(BaseModel):
    """Structured slots extracted from a natural-language dataset query."""

    disease: str | None = None
    tissue: str | None = None
    assay: str | None = None
    organism: str | None = None


class DataAccessReference(BaseModel):
    """Lightweight link to a repository page, API endpoint, or discoverable file path."""

    id: str = Field(..., description="Stable identifier within the candidate access list")
    label: str = Field(..., description="Human-readable reference label")
    url: str = Field(default="", description="HTTP(S) or FTP URL when available")
    access_type: str = Field(
        default="unknown",
        description=(
            "repository_page, direct_download, api, ftp, controlled, or unknown"
        ),
    )
    requires_auth: bool = Field(
        default=False,
        description="Whether access may require authentication or controlled approval",
    )
    notes: str = Field(default="", description="Short note about what this reference provides")


class AccessSummary(BaseModel):
    """Aggregate access signals for a dataset candidate."""

    text: str = Field(default="", description="One-line access summary for UI display")
    repository_page_url: str = Field(default="", description="Canonical study landing page")
    reference_count: int = Field(default=0, description="Number of discovered access references")
    direct_downloads_available: bool | None = Field(
        default=None,
        description="True when direct download links were discovered; null if unknown",
    )
    auth_may_be_required: bool | None = Field(
        default=None,
        description="True when any reference may require authentication",
    )


class DatasetCandidate(BaseModel):
    """Repository-agnostic dataset record with match evidence and score."""

    repository: str = Field(..., description="Source repository, e.g. GEO")
    accession: str = Field(..., description="Repository accession, e.g. GSE12345")
    title: str
    description: str = ""
    sample_count: int | None = None
    url: str = ""
    metadata_fields: dict[str, str] = Field(
        default_factory=dict,
        description="Normalized repository metadata used for evidence extraction",
    )
    requested_concepts: list[ConceptMapping] = Field(
        default_factory=list,
        description="Concepts requested by the user query",
    )
    matched_concepts: list[ConceptMapping] = Field(
        default_factory=list,
        description="Concepts supported by evidence in returned metadata",
    )
    observed_assay: str | None = None
    assay_mismatch: bool = Field(
        default=False,
        description="True when requested assay differs from observed assay in metadata",
    )
    observed_organism: str | None = None
    observed_disease: str | None = None
    observed_tissue: str | None = None
    evidence_snippets: list[EvidenceSnippet] = Field(default_factory=list)
    score: float = Field(
        default=0.0,
        description="Integrated display_rank_score (= match_tier × 10 + evidence_score)",
    )
    match_status: str = Field(
        default="partial",
        description=(
            "full, full_with_warnings, partial, or ambiguous_or_mixed "
            "based on evidence coverage and quality signals"
        ),
    )
    retrieval_strategy: str | None = Field(
        default=None,
        description="GEO search strategy that retrieved this candidate",
    )
    retrieval_search_term: str | None = Field(
        default=None,
        description="GEO query string that retrieved this candidate",
    )
    why_matched: list[str] = Field(default_factory=list)
    why_partial: list[str] = Field(default_factory=list)
    metadata_warnings: list[str] = Field(default_factory=list)
    evidence_conflicts: list[str] = Field(default_factory=list)
    score_breakdown: ScoreBreakdown | None = Field(
        default=None,
        description="Developer/debug audit of ranking inputs and evidence",
    )
    access_summary: AccessSummary | None = Field(
        default=None,
        description="Discovered access summary for UI and manifest export",
    )
    access_references: list[DataAccessReference] = Field(
        default_factory=list,
        description="Discovered repository, API, FTP, and file access references",
    )


class DatasetSearchCursor(BaseModel):
    """State for fetching the next GEO batch without re-running grounding."""

    query: str
    interpreted_query: InterpretedQuery
    concept_mappings: list[ConceptMapping] = Field(default_factory=list)
    strategy_offsets: dict[str, int] = Field(default_factory=dict)
    strategy_totals: dict[str, int] = Field(default_factory=dict)
    seen_ids: list[str] = Field(
        default_factory=list,
        description="GEO GDS UIDs already retrieved",
    )
    seen_accessions: list[str] = Field(
        default_factory=list,
        description="Repository accessions already ranked",
    )
    total_found: int = 0
    primary_total_found: int | None = None
    max_results: int = 15
    search_term: str | None = None
    has_more: bool = False


class DatasetSearchResult(BaseModel):
    """End-to-end dataset discovery response."""

    query: str
    interpreted_query: InterpretedQuery
    concept_mappings: list[ConceptMapping] = Field(default_factory=list)
    candidates: list[DatasetCandidate] = Field(default_factory=list)
    total_found: int = 0
    primary_total_found: int | None = Field(
        default=None,
        description="Hit count for the primary strict search strategy",
    )
    max_results: int | None = Field(
        default=None,
        description="Configured GEO retrieval/ranking limit for this search",
    )
    source: str = "NCBI GEO"
    repository: str = Field(default="GEO", description="Repository identifier searched")
    search_term: str | None = Field(
        default=None,
        description="Primary repository query string used when available",
    )
    search_strategies: list[dict[str, str | int]] = Field(
        default_factory=list,
        description="Multi-query retrieval strategies and hit counts",
    )
    has_more: bool = False
    retrieved_count: int = 0
    load_more_cursor: DatasetSearchCursor | None = Field(
        default=None,
        description="Opaque cursor for POST /api/dataset-search/more",
    )
