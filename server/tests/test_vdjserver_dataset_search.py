"""Tests for VDJServer dataset search connector."""

from unittest.mock import patch

from tools.vdjserver_dataset_search import (
    build_vdjserver_adc_filters,
    fetch_vdjserver_repository_records,
    normalize_vdjserver_record,
    search_vdjserver_datasets,
)

REPERTOIRE_RESPONSE = {
    "Info": {"title": "VDJServer"},
    "Repertoire": [
        {
            "repertoire_id": "3781383765129162260-242ac117-0001-012",
            "study": {
                "study_id": "PRJNA606979",
                "study_title": "Immune suppressive landscape in ESCC",
                "study_description": "Esophageal squamous cell carcinoma immune repertoire study.",
                "keywords_study": ["contains_tr"],
                "pub_ids": "PMID: 33293583",
            },
            "subject": {
                "species": {"id": "NCBITAXON:9606", "label": "Homo sapiens"},
                "diagnosis": [
                    {
                        "disease_diagnosis": {
                            "id": "DOID:3748",
                            "label": "esophagus squamous cell carcinoma",
                        }
                    }
                ],
            },
            "sample": [
                {
                    "sample_type": "ESCC_tumors",
                    "tissue": {"id": "UBERON:0002048", "label": "lung"},
                    "pcr_target": [{"pcr_target_locus": "TRB"}],
                    "sequencing_platform": "Illumina MiSeq",
                }
            ],
        }
    ],
}

FACET_RESPONSE = {
    "Info": {"title": "VDJServer"},
    "Facet": [{"study.study_id": "PRJNA606979", "count": 14}],
}


def _mock_post(url, *args, **kwargs):
    payload = kwargs.get("json") or {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            if payload.get("size") == 0:
                return FACET_RESPONSE
            return REPERTOIRE_RESPONSE

    return FakeResponse()


def test_build_vdjserver_adc_filters_strict_strategy():
    filters = build_vdjserver_adc_filters(
        strategy="strict",
        search_term="esophagus squamous cell carcinoma TCR lung",
        concept_mappings=[],
        interpreted={
            "disease": "esophagus squamous cell carcinoma",
            "assay": "TCR",
            "tissue": "lung",
            "organism": "human",
        },
    )

    assert filters["op"] == "and"
    fields = {item["content"]["field"]: item for item in filters["content"]}
    assert fields["subject.species.id"]["content"]["value"] == "NCBITAXON:9606"
    assert fields["subject.diagnosis.disease_diagnosis.label"]["content"]["value"] == (
        "esophagus squamous cell carcinoma"
    )
    assert fields["sample.tissue.label"]["content"]["value"] == "lung"
    assert fields["sample.pcr_target.pcr_target_locus"]["content"]["value"] == "TRB"


def test_search_vdjserver_datasets_returns_parsed_results():
    with patch("tools.vdjserver_dataset_search.requests.post", side_effect=_mock_post):
        result = search_vdjserver_datasets(
            "Find public immune repertoire datasets for esophagus squamous cell carcinoma lung TCR",
            max_results=5,
        )

    assert result["total_found"] == 1
    assert len(result["results"]) == 1
    assert result["results"][0]["accession"] == "PRJNA606979"
    assert result["repository"] == "VDJServer"


def test_normalize_vdjserver_record_populates_candidate_fields():
    record = {
        "accession": "PRJNA606979",
        "title": "Immune suppressive landscape in ESCC",
        "description": "Esophageal squamous cell carcinoma immune repertoire study.",
        "summary": "Esophageal squamous cell carcinoma immune repertoire study.",
        "condition_or_disease": "esophagus squamous cell carcinoma",
        "biosample_type": "lung",
        "assay_method": "TRB, Illumina MiSeq, contains_tr",
        "species": "Homo sapiens",
        "url": "https://www.ncbi.nlm.nih.gov/bioproject/PRJNA606979",
        "study_id": "PRJNA606979",
    }

    candidate = normalize_vdjserver_record(record)

    assert candidate is not None
    assert candidate.repository == "VDJServer"
    assert candidate.observed_disease == "esophagus squamous cell carcinoma"
    assert candidate.observed_tissue == "lung"
    assert candidate.metadata_fields["assay_method"] == "TRB, Illumina MiSeq, contains_tr"
    assert candidate.source_metadata["access_profile"] == "mixed"


def test_fetch_vdjserver_repository_records_uses_multi_strategy_search():
    with patch("tools.vdjserver_dataset_search.requests.post", side_effect=_mock_post) as mock_post:
        result = fetch_vdjserver_repository_records(
            [],
            max_results=5,
            query="Find public BCR repertoire datasets for COVID blood",
            interpreted_query={
                "disease": "COVID-19",
                "assay": "BCR",
                "tissue": "blood",
            },
        )

    assert result["repository"] == "VDJServer"
    assert result["records"]
    assert result["search_strategies"]
    first_payload = mock_post.call_args_list[0].kwargs["json"]
    filters = first_payload["filters"]
    assert filters["op"] == "and"
