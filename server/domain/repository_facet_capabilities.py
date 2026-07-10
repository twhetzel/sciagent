"""Facet capability inventory for dataset pipeline repositories.

Documents, per repository and facet slot:
- whether the API supports structured filtering at search time
- raw API field paths vs normalized ``metadata_fields`` keys
- evidence tier (structured CV, narrative, inferred)
- optional ``repository_vocab`` module for CV mapping
- SmartAPI-compatible semantic types (``x-parameterType`` / ``x-valueType`` alignment)

Human-readable tables: ``docs/repository-field-capabilities.md``.

When adding a new dataset pipeline repository, register capabilities here as part of
``docs/adding-a-source.md`` (section "Facet capability registry").

External registries: SciAgent facet slots align with `Biolink Model
<https://w3id.org/biolink/vocab/>`_ semantic types and `identifiers.org
<https://identifiers.org/>`_ namespaces, following the `SmartAPI
<https://smart-api.info/>`_ OpenAPI extension pattern (``x-parameterType``,
``x-valueType``, ``x-responseValueType``). Dataset repositories (GEO, ImmPort,
OmicsDI, …) are not fully catalogued in SmartAPI today; this module is SciAgent's
aggregated source of truth for those adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .dataset_repository_registry import (
    GEO_REPOSITORY,
    GXA_REPOSITORY,
    IMMPORT_REPOSITORY,
    OMICSDI_REPOSITORY,
    PROTEOMEXCHANGE_REPOSITORY,
    TEXT_BROAD_REPOSITORIES,
    VDJSERVER_REPOSITORY,
    VIVLI_REPOSITORY,
)

FacetSlot = Literal["disease", "tissue", "assay", "organism"]
EvidenceTier = Literal["structured_cv", "structured", "narrative", "inferred", "mixed"]

# Canonical normalized keys used by evidence_extraction.py (SciAgent facet schema).
CANONICAL_DISEASE_FIELD = "condition_or_disease"
CANONICAL_TISSUE_FIELD = "biosample_type"
CANONICAL_ASSAY_FIELD = "assay_method"
CANONICAL_ORGANISM_FIELD = "taxon"
NARRATIVE_FIELDS = ("title", "summary")

BIOLINK_VOCAB = "https://w3id.org/biolink/vocab"


@dataclass(frozen=True)
class FacetSlotSemantics:
    """Shared semantic typing for a SciAgent facet slot (SmartAPI / Biolink aligned)."""

    slot: FacetSlot
    semantic_type_uri: str
    value_type_uris: tuple[str, ...]
    description: str


# SciAgent facet slots → Biolink semantic types + accepted identifier namespaces.
# Mirrors SmartAPI x-parameterType / x-valueType recommendations per slot.
FACET_SLOT_SEMANTICS: dict[FacetSlot, FacetSlotSemantics] = {
    "disease": FacetSlotSemantics(
        slot="disease",
        semantic_type_uri=f"{BIOLINK_VOCAB}/Disease",
        value_type_uris=(
            "http://identifiers.org/mondo",
            "http://identifiers.org/doid",
            "http://identifiers.org/efo",
        ),
        description="Disease or disorder (MONDO / DOID / EFO grounded)",
    ),
    "tissue": FacetSlotSemantics(
        slot="tissue",
        semantic_type_uri=f"{BIOLINK_VOCAB}/AnatomicalEntity",
        value_type_uris=(
            "http://identifiers.org/uberon",
            "http://identifiers.org/cl",
        ),
        description="Anatomy, biosample, or cell type (UBERON / CL grounded)",
    ),
    "assay": FacetSlotSemantics(
        slot="assay",
        semantic_type_uri=f"{BIOLINK_VOCAB}/Assay",
        value_type_uris=(
            "http://identifiers.org/obi",
            "http://identifiers.org/go",
            "http://identifiers.org/ncit",
        ),
        description="Experimental assay or omics investigation (OBI / GO / NCIT grounded)",
    ),
    "organism": FacetSlotSemantics(
        slot="organism",
        semantic_type_uri=f"{BIOLINK_VOCAB}/OrganismTaxon",
        value_type_uris=("http://identifiers.org/taxonomy",),
        description="Species or strain (NCBI Taxonomy)",
    ),
}


def facet_slot_semantics(slot: FacetSlot) -> FacetSlotSemantics:
    return FACET_SLOT_SEMANTICS[slot]


@dataclass(frozen=True)
class FacetSlotCapability:
    """One facet slot's search, response, and evidence behavior for a repository."""

    slot: FacetSlot
    api_filterable: bool
    api_param_or_clause: str | None
    raw_response_fields: tuple[str, ...]
    normalized_fields: tuple[str, ...]
    evidence_tier: EvidenceTier
    narrative_fallback: bool = True
    semantic_type_uri: str | None = None
    value_type_uris: tuple[str, ...] = ()

    def resolved_semantic_type_uri(self) -> str:
        if self.semantic_type_uri:
            return self.semantic_type_uri
        return facet_slot_semantics(self.slot).semantic_type_uri

    def resolved_value_type_uris(self) -> tuple[str, ...]:
        if self.value_type_uris:
            return self.value_type_uris
        return facet_slot_semantics(self.slot).value_type_uris

    def smartapi_response_value_types(self) -> tuple[dict[str, str], ...]:
        """SmartAPI ``x-responseValueType``-style annotations for structured raw fields."""
        if self.evidence_tier == "narrative":
            return ()
        value_type = (
            self.resolved_value_type_uris()[0]
            if self.resolved_value_type_uris()
            else self.resolved_semantic_type_uri()
        )
        return tuple(
            {"x-path": path, "x-valueType": value_type}
            for path in self.raw_response_fields
            if path and path not in NARRATIVE_FIELDS
        )

    def smartapi_parameter_annotation(self) -> dict[str, Any]:
        """SmartAPI parameter annotation for search-time facet filters."""
        return {
            "x-parameterType": self.resolved_semantic_type_uri(),
            "x-valueType": list(self.resolved_value_type_uris()),
        }


def _make_slot_capability(
    slot: FacetSlot,
    *,
    api_filterable: bool,
    api_param_or_clause: str | None,
    raw_response_fields: tuple[str, ...],
    normalized_fields: tuple[str, ...],
    evidence_tier: EvidenceTier,
    narrative_fallback: bool = True,
    semantic_type_uri: str | None = None,
    value_type_uris: tuple[str, ...] = (),
) -> FacetSlotCapability:
    """Build a slot capability with default Biolink / identifiers.org semantics."""
    return FacetSlotCapability(
        slot=slot,
        api_filterable=api_filterable,
        api_param_or_clause=api_param_or_clause,
        raw_response_fields=raw_response_fields,
        normalized_fields=normalized_fields,
        evidence_tier=evidence_tier,
        narrative_fallback=narrative_fallback,
        semantic_type_uri=semantic_type_uri,
        value_type_uris=value_type_uris,
    )


@dataclass(frozen=True)
class RepositoryFacetCapability:
    """Facet capabilities for one dataset pipeline repository."""

    repository: str
    tool_module: str
    api_summary: str
    repository_vocab_module: str | None
    text_broad: bool
    facet_slots: tuple[FacetSlotCapability, ...]
    special_notes: tuple[str, ...] = field(default_factory=tuple)

    def slot_capability(self, slot: FacetSlot) -> FacetSlotCapability | None:
        for item in self.facet_slots:
            if item.slot == slot:
                return item
        return None

    def queryable_slots(self) -> tuple[FacetSlot, ...]:
        return tuple(item.slot for item in self.facet_slots if item.api_filterable)

    def structured_evidence_slots(self) -> tuple[FacetSlot, ...]:
        return tuple(
            item.slot
            for item in self.facet_slots
            if item.evidence_tier in {"structured_cv", "structured", "inferred", "mixed"}
            and item.normalized_fields
            and item.normalized_fields[0] not in NARRATIVE_FIELDS
        )


def _geo_capability() -> RepositoryFacetCapability:
    narrative = ("title", "summary")
    return RepositoryFacetCapability(
        repository=GEO_REPOSITORY,
        tool_module="tools.geo_dataset_search",
        api_summary="NCBI E-utilities esearch/esummary (db=gds, term=…)",
        repository_vocab_module=None,
        text_broad=False,
        facet_slots=(
            _make_slot_capability(
                "disease",
                api_filterable=True,
                api_param_or_clause="term (grounded synonyms AND-joined via build_geo_search_term)",
                raw_response_fields=("title", "summary"),
                normalized_fields=narrative,
                evidence_tier="narrative",
            ),
            _make_slot_capability(
                "tissue",
                api_filterable=True,
                api_param_or_clause="term (grounded synonyms AND-joined)",
                raw_response_fields=("samples[].title", "title", "summary"),
                normalized_fields=("title", "summary", "sample_titles"),
                evidence_tier="narrative",
            ),
            _make_slot_capability(
                "assay",
                api_filterable=True,
                api_param_or_clause="term (grounded synonyms AND-joined)",
                raw_response_fields=("gdstype", "platformtitle", "ptechtype"),
                normalized_fields=("gdstype", "platformtitle", "ptechtype", "assay_method"),
                evidence_tier="inferred",
            ),
            _make_slot_capability(
                "organism",
                api_filterable=False,
                api_param_or_clause=None,
                raw_response_fields=("taxon", "platformtaxa", "samplestaxa"),
                normalized_fields=(CANONICAL_ORGANISM_FIELD, "platformtaxa", "sample_titles"),
                evidence_tier="structured",
            ),
        ),
        special_notes=(
            "No structured facet API — all slots are free-text Entrez query terms.",
            "gdstype is the primary assay signal (GDS_TYPE_ASSAY_HINTS in evidence_extraction.py).",
        ),
    )


def _gxa_capability() -> RepositoryFacetCapability:
    narrative = NARRATIVE_FIELDS
    return RepositoryFacetCapability(
        repository=GXA_REPOSITORY,
        tool_module="tools.expression_atlas",
        api_summary="EBI Search atlas-experiments + GXA JSON detail",
        repository_vocab_module=None,
        text_broad=False,
        facet_slots=(
            _make_slot_capability(
                "disease",
                api_filterable=True,
                api_param_or_clause="query (space-joined facet terms)",
                raw_response_fields=("description",),
                normalized_fields=narrative,
                evidence_tier="narrative",
            ),
            _make_slot_capability(
                "tissue",
                api_filterable=True,
                api_param_or_clause="query (space-joined facet terms)",
                raw_response_fields=(),
                normalized_fields=narrative,
                evidence_tier="narrative",
            ),
            _make_slot_capability(
                "assay",
                api_filterable=True,
                api_param_or_clause="query (space-joined facet terms)",
                raw_response_fields=("experimenttype", "assaytype", "type"),
                normalized_fields=("gxa_experiment_type", "gxa_observed_assay", "gdstype"),
                evidence_tier="inferred",
            ),
            _make_slot_capability(
                "organism",
                api_filterable=False,
                api_param_or_clause="species (post-filter on fetch, not in facet query string)",
                raw_response_fields=("species",),
                normalized_fields=(CANONICAL_ORGANISM_FIELD,),
                evidence_tier="structured",
            ),
        ),
        special_notes=(
            "Assay inferred from gxa_experiment_type via domain/gxa_assay.py.",
            "gdstype in metadata is populated from GXA experiment_type (GEO field reuse).",
        ),
    )


def _immport_capability() -> RepositoryFacetCapability:
    cv_disease = (CANONICAL_DISEASE_FIELD,)
    cv_tissue = (CANONICAL_TISSUE_FIELD,)
    cv_assay = (CANONICAL_ASSAY_FIELD,)
    return RepositoryFacetCapability(
        repository=IMMPORT_REPOSITORY,
        tool_module="tools.immport_dataset_search",
        api_summary="ImmPort Shared Data GET /data/query/api/search/study",
        repository_vocab_module="domain.repository_vocab.immport_vocab",
        text_broad=True,
        facet_slots=(
            _make_slot_capability(
                "disease",
                api_filterable=True,
                api_param_or_clause="conditionOrDisease (CV)",
                raw_response_fields=("condition_or_disease",),
                normalized_fields=cv_disease,
                evidence_tier="structured_cv",
            ),
            _make_slot_capability(
                "tissue",
                api_filterable=True,
                api_param_or_clause="biosampleType (CV)",
                raw_response_fields=("biosample_type",),
                normalized_fields=cv_tissue,
                evidence_tier="structured_cv",
            ),
            _make_slot_capability(
                "assay",
                api_filterable=True,
                api_param_or_clause="assayMethod (CV)",
                raw_response_fields=("assay_method",),
                normalized_fields=cv_assay + ("gdstype",),
                evidence_tier="structured_cv",
            ),
            _make_slot_capability(
                "organism",
                api_filterable=True,
                api_param_or_clause="species (e.g. Homo sapiens)",
                raw_response_fields=("species",),
                normalized_fields=(CANONICAL_ORGANISM_FIELD,),
                evidence_tier="structured",
                narrative_fallback=False,
            ),
        ),
        special_notes=(
            "Reference CV-backed source for IMMPORT_*_FIELD constants in evidence_extraction.py.",
            "text_broad uses free-text term param without facet filters.",
        ),
    )


def _vivli_capability() -> RepositoryFacetCapability:
    return RepositoryFacetCapability(
        repository=VIVLI_REPOSITORY,
        tool_module="tools.vivli_dataset_search",
        api_summary="NIAID Discovery GET /v1/query (q=…)",
        repository_vocab_module="domain.repository_vocab.vivli_vocab",
        text_broad=True,
        facet_slots=(
            _make_slot_capability(
                "disease",
                api_filterable=True,
                api_param_or_clause='healthCondition.name:"{value}"',
                raw_response_fields=("healthCondition[].name",),
                normalized_fields=(CANONICAL_DISEASE_FIELD,),
                evidence_tier="structured",
            ),
            _make_slot_capability(
                "tissue",
                api_filterable=True,
                api_param_or_clause='sample.sampleType.name:"{value}" OR "{value}"',
                raw_response_fields=("sample.sampleType.name",),
                normalized_fields=(CANONICAL_TISSUE_FIELD,),
                evidence_tier="structured",
            ),
            _make_slot_capability(
                "assay",
                api_filterable=True,
                api_param_or_clause='"{value}" (quoted free-text, not field-scoped)',
                raw_response_fields=("measurementTechnique[].name",),
                normalized_fields=(CANONICAL_ASSAY_FIELD, "gdstype"),
                evidence_tier="mixed",
            ),
            _make_slot_capability(
                "organism",
                api_filterable=False,
                api_param_or_clause="post-filter _species_matches (defaults Homo sapiens)",
                raw_response_fields=("species",),
                normalized_fields=(CANONICAL_ORGANISM_FIELD,),
                evidence_tier="structured",
            ),
        ),
        special_notes=(
            "Clinical trial catalog; queries scoped to Vivli / accessclinicaldata@NIAID.",
            "Assay search is the weakest facet (generic quoted term).",
        ),
    )


def _omicsdi_capability() -> RepositoryFacetCapability:
    return RepositoryFacetCapability(
        repository=OMICSDI_REPOSITORY,
        tool_module="tools.omicsdi_dataset_search",
        api_summary="OmicsDI GET /ws/dataset/search + detail /ws/dataset/{source}/{id}",
        repository_vocab_module="domain.repository_vocab.omicsdi_vocab",
        text_broad=True,
        facet_slots=(
            _make_slot_capability(
                "disease",
                api_filterable=True,
                api_param_or_clause='disease:"{value}"',
                raw_response_fields=("additional.disease[]",),
                normalized_fields=(CANONICAL_DISEASE_FIELD,),
                evidence_tier="structured_cv",
            ),
            _make_slot_capability(
                "tissue",
                api_filterable=True,
                api_param_or_clause='tissue:"{value}"',
                raw_response_fields=("additional.tissue[]",),
                normalized_fields=(CANONICAL_TISSUE_FIELD,),
                evidence_tier="structured_cv",
            ),
            _make_slot_capability(
                "assay",
                api_filterable=True,
                api_param_or_clause='omics_type:"{value}" or technology_type:"{value}"',
                raw_response_fields=("omicsType[]", "additional.technology_type[]"),
                normalized_fields=(
                    "omicsdi_omics_type",
                    "omicsdi_observed_assay",
                    CANONICAL_ASSAY_FIELD,
                    "gdstype",
                ),
                evidence_tier="inferred",
            ),
            _make_slot_capability(
                "organism",
                api_filterable=True,
                api_param_or_clause='TAXONOMY:"{ncbi_taxon_id}"',
                raw_response_fields=("organisms[].name",),
                normalized_fields=(CANONICAL_ORGANISM_FIELD,),
                evidence_tier="structured",
            ),
        ),
        special_notes=(
            "Detail fetch enriches disease/tissue when search hits lack structured fields.",
            "omics_type is the primary assay facet at search time.",
        ),
    )


def _proteomexchange_capability() -> RepositoryFacetCapability:
    base = _omicsdi_capability()
    return RepositoryFacetCapability(
        repository=PROTEOMEXCHANGE_REPOSITORY,
        tool_module="tools.proteomexchange_dataset_search",
        api_summary="OmicsDI search scoped to PX member repositories",
        repository_vocab_module="domain.repository_vocab.proteomexchange_vocab",
        text_broad=True,
        facet_slots=base.facet_slots,
        special_notes=(
            "Same OmicsDI API as OmicsDI with repository:pride OR repository:MassIVE … scope.",
            "Always includes omics_type:\"Proteomics\" unless a more specific assay clause applies.",
            "Proteomics-only pipeline.",
        ),
    )


def _vdjserver_capability() -> RepositoryFacetCapability:
    return RepositoryFacetCapability(
        repository=VDJSERVER_REPOSITORY,
        tool_module="tools.vdjserver_dataset_search",
        api_summary="AIRR ADC POST /airr/v1/repertoire (JSON filters)",
        repository_vocab_module="domain.repository_vocab.vdjserver_vocab",
        text_broad=True,
        facet_slots=(
            _make_slot_capability(
                "disease",
                api_filterable=True,
                api_param_or_clause="subject.diagnosis.disease_diagnosis.label contains",
                raw_response_fields=("subject.diagnosis[].disease_diagnosis.label",),
                normalized_fields=(CANONICAL_DISEASE_FIELD,),
                evidence_tier="structured",
            ),
            _make_slot_capability(
                "tissue",
                api_filterable=True,
                api_param_or_clause="sample.tissue.label contains",
                raw_response_fields=("sample[].tissue.label", "sample_type"),
                normalized_fields=(CANONICAL_TISSUE_FIELD,),
                evidence_tier="structured",
            ),
            _make_slot_capability(
                "assay",
                api_filterable=True,
                api_param_or_clause="sample.pcr_target.pcr_target_locus = or study.study_title contains",
                raw_response_fields=(
                    "sample[].pcr_target[].pcr_target_locus",
                    "sequencing_platform",
                    "study.keywords_study",
                ),
                normalized_fields=(CANONICAL_ASSAY_FIELD, "airr_observed_assay", "gdstype"),
                evidence_tier="inferred",
            ),
            _make_slot_capability(
                "organism",
                api_filterable=True,
                api_param_or_clause="subject.species.id = (e.g. NCBITAXON:9606)",
                raw_response_fields=("subject.species.id", "subject.species.label"),
                normalized_fields=(CANONICAL_ORGANISM_FIELD,),
                evidence_tier="structured",
            ),
        ),
        special_notes=(
            "Immune-repertoire-only; BCR maps to IGH, TCR to TRB locus filters.",
            "text_broad/adhoc uses study.study_title contains.",
        ),
    )


FACET_CAPABILITY_REGISTRY: dict[str, RepositoryFacetCapability] = {
    GEO_REPOSITORY: _geo_capability(),
    GXA_REPOSITORY: _gxa_capability(),
    IMMPORT_REPOSITORY: _immport_capability(),
    VIVLI_REPOSITORY: _vivli_capability(),
    OMICSDI_REPOSITORY: _omicsdi_capability(),
    PROTEOMEXCHANGE_REPOSITORY: _proteomexchange_capability(),
    VDJSERVER_REPOSITORY: _vdjserver_capability(),
}


def get_facet_capability(repository: str) -> RepositoryFacetCapability:
    """Return facet capabilities for a dataset pipeline repository."""
    try:
        return FACET_CAPABILITY_REGISTRY[repository]
    except KeyError as exc:
        raise ValueError(f"No facet capability registered for repository: {repository}") from exc


def all_facet_capabilities() -> tuple[RepositoryFacetCapability, ...]:
    """Return all registered repository facet capabilities in stable order."""
    return tuple(FACET_CAPABILITY_REGISTRY[name] for name in sorted(FACET_CAPABILITY_REGISTRY))


def repositories_with_structured_facet_search() -> frozenset[str]:
    """Repositories that expose at least one CV or field-scoped facet filter."""
    result: set[str] = set()
    for repo, cap in FACET_CAPABILITY_REGISTRY.items():
        for slot in cap.facet_slots:
            if slot.api_filterable and slot.api_param_or_clause:
                clause = slot.api_param_or_clause.lower()
                if "term" not in clause and "query" not in clause and "quoted free-text" not in clause:
                    result.add(repo)
                    break
                if slot.evidence_tier == "structured_cv":
                    result.add(repo)
                    break
    return frozenset(result)
