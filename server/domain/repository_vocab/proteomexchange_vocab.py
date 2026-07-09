"""ProteomeXchange search facet normalization (OmicsDI REST field syntax)."""

from __future__ import annotations

from .omicsdi_vocab import omicsdi_assay_filter_clauses, resolve_omicsdi_facet_value


def resolve_proteomexchange_facet_value(slot: str, term: str | None) -> str | None:
    """Map a grounded label to a ProteomeXchange/OmicsDI query facet value."""
    return resolve_omicsdi_facet_value(slot, term)


def proteomexchange_assay_filter_clauses(assay_value: str | None) -> list[str]:
    """Return query clauses for proteomics assay / omics-type filters."""
    if not assay_value:
        return ['omics_type:"Proteomics"']
    normalized = resolve_omicsdi_facet_value("assay", assay_value)
    clauses = omicsdi_assay_filter_clauses(normalized or assay_value)
    if any(
        clause.startswith("omics_type:") or clause.startswith("technology_type:")
        for clause in clauses
    ):
        return clauses
    return ['omics_type:"Proteomics"']


def map_term_to_proteomexchange_facet(slot: str, term: str | None) -> str | None:
    """Public alias for repository vocab tests and adapters."""
    return resolve_proteomexchange_facet_value(slot, term)
