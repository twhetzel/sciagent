"""Tests for the repository facet capability registry."""

from __future__ import annotations

import importlib

from domain.dataset_repository_registry import (
    GEO_REPOSITORY,
    GXA_REPOSITORY,
    IMMPORT_REPOSITORY,
    OMICSDI_REPOSITORY,
    PROTEOMEXCHANGE_REPOSITORY,
    TEXT_BROAD_REPOSITORIES,
    VDJSERVER_REPOSITORY,
    VIVLI_REPOSITORY,
    get_repository_spec,
    supported_repositories,
)
from domain.repository_facet_capabilities import (
    BIOLINK_VOCAB,
    CANONICAL_ASSAY_FIELD,
    CANONICAL_DISEASE_FIELD,
    CANONICAL_ORGANISM_FIELD,
    CANONICAL_TISSUE_FIELD,
    FACET_CAPABILITY_REGISTRY,
    FACET_SLOT_SEMANTICS,
    all_facet_capabilities,
    facet_slot_semantics,
    get_facet_capability,
)


def test_facet_capability_registry_covers_all_supported_repositories():
    assert set(FACET_CAPABILITY_REGISTRY) == set(supported_repositories())


def test_text_broad_flag_matches_repository_registry():
    for repository in supported_repositories():
        capability = get_facet_capability(repository)
        assert capability.text_broad == (repository in TEXT_BROAD_REPOSITORIES)


def test_immport_has_structured_cv_for_core_facets():
    capability = get_facet_capability(IMMPORT_REPOSITORY)
    for slot in ("disease", "tissue", "assay"):
        item = capability.slot_capability(slot)
        assert item is not None
        assert item.api_filterable is True
        assert item.evidence_tier == "structured_cv"


def test_geo_disease_is_narrative_only():
    capability = get_facet_capability(GEO_REPOSITORY)
    disease = capability.slot_capability("disease")
    assert disease is not None
    assert disease.evidence_tier == "narrative"
    assert CANONICAL_DISEASE_FIELD not in disease.normalized_fields


def test_cv_backed_repositories_use_canonical_metadata_fields():
    for repository in (IMMPORT_REPOSITORY, OMICSDI_REPOSITORY, VIVLI_REPOSITORY, VDJSERVER_REPOSITORY):
        capability = get_facet_capability(repository)
        disease = capability.slot_capability("disease")
        tissue = capability.slot_capability("tissue")
        assert disease is not None and tissue is not None
        assert CANONICAL_DISEASE_FIELD in disease.normalized_fields
        assert CANONICAL_TISSUE_FIELD in tissue.normalized_fields


def test_repository_vocab_module_imports_when_declared():
    for capability in all_facet_capabilities():
        if not capability.repository_vocab_module:
            continue
        module = importlib.import_module(capability.repository_vocab_module)
        assert module is not None


def test_repository_spec_exposes_facet_capabilities():
    spec = get_repository_spec(GXA_REPOSITORY)
    assert spec.facet_capabilities.repository == GXA_REPOSITORY
    assert spec.facet_capabilities.tool_module == "tools.expression_atlas"


def test_proteomexchange_inherits_omicsdi_facet_shape():
    px = get_facet_capability(PROTEOMEXCHANGE_REPOSITORY)
    omicsdi = get_facet_capability(OMICSDI_REPOSITORY)
    assert len(px.facet_slots) == len(omicsdi.facet_slots)
    assert px.repository_vocab_module == "domain.repository_vocab.proteomexchange_vocab"


def test_assay_field_present_for_assay_capable_repos():
    for capability in all_facet_capabilities():
        assay = capability.slot_capability("assay")
        assert assay is not None
        if assay.evidence_tier in {"structured_cv", "inferred", "mixed"}:
            assert CANONICAL_ASSAY_FIELD in assay.normalized_fields or "gdstype" in assay.normalized_fields


def test_organism_field_uses_taxon_when_structured():
    for repository in (IMMPORT_REPOSITORY, OMICSDI_REPOSITORY, VDJSERVER_REPOSITORY):
        organism = get_facet_capability(repository).slot_capability("organism")
        assert organism is not None
        assert CANONICAL_ORGANISM_FIELD in organism.normalized_fields


def test_facet_slot_semantics_cover_all_slots():
    assert set(FACET_SLOT_SEMANTICS) == {"disease", "tissue", "assay", "organism"}
    disease = facet_slot_semantics("disease")
    assert disease.semantic_type_uri == f"{BIOLINK_VOCAB}/Disease"
    assert "http://identifiers.org/mondo" in disease.value_type_uris


def test_slot_capabilities_resolve_default_semantic_types():
    disease = get_facet_capability(IMMPORT_REPOSITORY).slot_capability("disease")
    assert disease is not None
    assert disease.resolved_semantic_type_uri().endswith("/Disease")
    assert disease.resolved_value_type_uris()[0].startswith("http://identifiers.org/")


def test_immport_disease_smartapi_response_annotations():
    disease = get_facet_capability(IMMPORT_REPOSITORY).slot_capability("disease")
    assert disease is not None
    annotations = disease.smartapi_response_value_types()
    assert annotations == (
        {
            "x-path": "condition_or_disease",
            "x-valueType": "http://identifiers.org/mondo",
        },
    )


def test_narrative_geo_disease_has_no_smartapi_response_annotations():
    disease = get_facet_capability(GEO_REPOSITORY).slot_capability("disease")
    assert disease is not None
    assert disease.smartapi_response_value_types() == ()
    assert disease.smartapi_parameter_annotation()["x-parameterType"].endswith("/Disease")
