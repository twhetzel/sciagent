"""Curated alias cache and fallback provider for dataset discovery grounding."""

from __future__ import annotations

import re

from domain.dataset_search import ConceptMapping

from .base import CONFIDENCE_BY_MATCH

SEED_CONCEPTS: dict[str, dict] = {
    "ulcerative colitis": {
        "slot": "disease",
        "curie": "MONDO:0005101",
        "label": "ulcerative colitis",
        "ontology": "MONDO",
        "iri": "http://purl.obolibrary.org/obo/MONDO_0005101",
        "synonyms": ["ulcerative colitis", "UC", "colitis ulcerative"],
    },
    "colon": {
        "slot": "tissue",
        "curie": "UBERON:0001155",
        "label": "colon",
        "ontology": "UBERON",
        "iri": "http://purl.obolibrary.org/obo/UBERON_0001155",
        "synonyms": ["colon", "colonic", "large intestine", "large bowel"],
    },
    "RNA-seq": {
        "slot": "assay",
        "curie": "OBI:0002117",
        "label": "RNA-seq",
        "ontology": "OBI",
        "iri": "http://purl.obolibrary.org/obo/OBI_0002117",
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
        "iri": "https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=9606",
        "synonyms": ["human", "Homo sapiens", "homo sapiens", "Homo sapiens (human)"],
    },
}


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


class CuratedAliasProvider:
    """Local alias cache and fallback when dynamic lookup is unavailable."""

    name = "curated"

    def lookup(self, slot: str, term: str) -> list[ConceptMapping]:
        normalized_term = _normalize_text(term)
        candidates: list[ConceptMapping] = []

        for seed_term, seed in SEED_CONCEPTS.items():
            if seed["slot"] != slot:
                continue

            searchable = {_normalize_text(seed_term), _normalize_text(seed["label"])}
            searchable.update(_normalize_text(s) for s in seed["synonyms"])

            if normalized_term not in searchable:
                continue

            match_type = (
                "curated_exact"
                if normalized_term in {_normalize_text(seed_term), _normalize_text(seed["label"])}
                else "curated_synonym"
            )
            candidates.append(
                ConceptMapping(
                    slot=slot,
                    query_term=term,
                    curie=seed["curie"],
                    label=seed["label"],
                    ontology=seed["ontology"],
                    iri=seed.get("iri"),
                    synonyms=list(seed["synonyms"]),
                    match_type=match_type,
                    source=self.name,
                    confidence=CONFIDENCE_BY_MATCH[match_type],
                    explanation=f"Matched curated alias for {slot}={term}",
                )
            )

        return candidates
