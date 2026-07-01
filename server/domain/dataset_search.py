"""Pydantic models for ontology-grounded dataset discovery."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
    synonyms: list[str] = Field(default_factory=list, description="Search synonyms")


class InterpretedQuery(BaseModel):
    """Structured slots extracted from a natural-language dataset query."""

    disease: str | None = None
    tissue: str | None = None
    assay: str | None = None
    organism: str | None = None


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
    observed_organism: str | None = None
    observed_disease: str | None = None
    observed_tissue: str | None = None
    evidence_snippets: list[EvidenceSnippet] = Field(default_factory=list)
    score: float = 0.0
    match_status: str = Field(
        default="partial",
        description="full, partial, or conflict",
    )
    why_matched: list[str] = Field(default_factory=list)
    why_partial: list[str] = Field(default_factory=list)
    conflicting_assays: list[str] = Field(default_factory=list)


class DatasetSearchResult(BaseModel):
    """End-to-end dataset discovery response."""

    query: str
    interpreted_query: InterpretedQuery
    concept_mappings: list[ConceptMapping] = Field(default_factory=list)
    candidates: list[DatasetCandidate] = Field(default_factory=list)
    total_found: int = 0
    source: str = "NCBI GEO"
