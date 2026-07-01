"""Curated seed mappings for ontology-grounded dataset search."""

from __future__ import annotations

from .dataset_search import ConceptMapping, InterpretedQuery

SEED_CONCEPTS: dict[str, dict] = {
    "ulcerative colitis": {
        "slot": "disease",
        "curie": "MONDO:0005101",
        "label": "ulcerative colitis",
        "ontology": "MONDO",
        "synonyms": ["ulcerative colitis", "UC", "colitis ulcerative"],
    },
    "colon": {
        "slot": "tissue",
        "curie": "UBERON:0001155",
        "label": "colon",
        "ontology": "UBERON",
        "synonyms": ["colon", "colonic", "large intestine", "large bowel"],
    },
    "RNA-seq": {
        "slot": "assay",
        "curie": "OBI:0002117",
        "label": "RNA-seq",
        "ontology": "OBI",
        "synonyms": [
            "RNA-seq",
            "RNA seq",
            "RNA sequencing",
            "RNAseq",
            "transcriptome profiling",
            "RNA-Seq",
        ],
    },
    "human": {
        "slot": "organism",
        "curie": "NCBITaxon:9606",
        "label": "Homo sapiens",
        "ontology": "NCBITaxon",
        "synonyms": ["human", "Homo sapiens", "homo sapiens", "Homo sapiens (human)"],
    },
}


def _mapping_for_term(slot: str, query_term: str) -> ConceptMapping | None:
    seed = SEED_CONCEPTS.get(query_term)
    if not seed or seed["slot"] != slot:
        return None
    return ConceptMapping(
        slot=slot,
        query_term=query_term,
        curie=seed["curie"],
        label=seed["label"],
        ontology=seed["ontology"],
        synonyms=list(seed["synonyms"]),
    )


def ground_interpreted_query(interpreted: InterpretedQuery) -> list[ConceptMapping]:
    """Map interpreted query slots to curated ontology concepts."""
    mappings: list[ConceptMapping] = []

    slot_values = [
        ("disease", interpreted.disease),
        ("tissue", interpreted.tissue),
        ("assay", interpreted.assay),
        ("organism", interpreted.organism),
    ]
    for slot, term in slot_values:
        if not term:
            continue
        mapping = _mapping_for_term(slot, term)
        if mapping:
            mappings.append(mapping)

    return mappings


def search_terms_for_mapping(mapping: ConceptMapping) -> list[str]:
    """All terms to use when searching repositories for a grounded concept."""
    terms = {mapping.label.lower(), mapping.query_term.lower()}
    terms.update(s.lower() for s in mapping.synonyms)
    return sorted(terms)


def build_geo_search_term(mappings: list[ConceptMapping]) -> str:
    """Build a GEO query from grounded concept synonym groups."""
    if not mappings:
        return ""

    groups: list[str] = []
    for mapping in mappings:
        terms = search_terms_for_mapping(mapping)
        if len(terms) == 1:
            groups.append(f'"{terms[0]}"')
        else:
            quoted = [f'"{term}"' if " " in term else term for term in terms]
            groups.append(f"({' OR '.join(quoted)})")

    return " AND ".join(groups)
