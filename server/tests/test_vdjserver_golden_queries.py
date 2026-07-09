"""Integration-style tests for VDJServer golden query interpretation and search params."""

from domain.ontology_grounding import enrich_concept_mappings, ground_interpreted_query
from domain.query_interpretation import interpret_dataset_query
from tools.vdjserver_dataset_search import build_vdjserver_adc_filters

COVID_BCR_QUERY = "Find public BCR repertoire datasets for COVID-19 blood."
ESCC_TCR_QUERY = (
    "Find public immune repertoire datasets for esophagus squamous cell carcinoma lung TCR."
)


def test_covid_bcr_query_builds_vdjserver_facet_search():
    interpreted = interpret_dataset_query(COVID_BCR_QUERY)
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))

    filters = build_vdjserver_adc_filters(
        strategy="strict",
        search_term="COVID-19 BCR blood",
        concept_mappings=mappings,
        interpreted=interpreted,
    )

    assert filters["op"] == "and"
    fields = {item["content"]["field"] for item in filters["content"]}
    assert "subject.diagnosis.disease_diagnosis.label" in fields
    assert "sample.tissue.label" in fields
    assert "sample.pcr_target.pcr_target_locus" in fields


def test_covid_bcr_query_interprets_disease_tissue_and_assay():
    interpreted = interpret_dataset_query(COVID_BCR_QUERY)
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))

    assert interpreted.disease == "COVID-19"
    assert interpreted.tissue == "blood"
    assert interpreted.assay == "BCR repertoire"

    slots = {mapping.slot for mapping in mappings}
    assert slots == {"disease", "tissue", "assay"}
    assay = next(mapping for mapping in mappings if mapping.slot == "assay")
    assert assay.curie == "NCIT:C189103"
    assert assay.label == "B cell receptor repertoire sequencing"


def test_escc_tcr_query_interprets_disease_and_tissue():
    interpreted = interpret_dataset_query(ESCC_TCR_QUERY)
    mappings = enrich_concept_mappings(ground_interpreted_query(interpreted))

    assert interpreted.disease == "esophagus squamous cell carcinoma"
    assert interpreted.tissue == "lung"
    tissue = next(mapping for mapping in mappings if mapping.slot == "tissue")
    assert tissue.curie == "UBERON:0002048"
