# VDJServer golden queries

Representative immune repertoire dataset-discovery queries for regression testing against the VDJServer AIRR Data Commons connector.

## Queries

| Query | Expected facets | Notes |
|-------|-----------------|-------|
| `Find public BCR repertoire datasets for COVID-19 blood.` | disease=COVID-19, tissue=blood, assay=BCR repertoire | Regex + curated interpretation; strict strategy filters disease label, blood tissue, and IGH locus |
| `Find public immune repertoire datasets for esophagus squamous cell carcinoma lung TCR.` | disease=esophagus squamous cell carcinoma, tissue=lung, assay≈TCR | ESCC study `PRJNA606979` is a known hit in VDJServer |

## Automated coverage

- `tests/test_vdjserver_golden_queries.py` — interpretation + ADC filter construction
- `tests/test_vdjserver_dataset_search.py` — mocked adapter strategies and normalization
- `tests/test_vdjserver_evidence_extraction.py` — structured metadata evidence
- `tests/test_vdjserver_vocab.py` — repository facet aliases

Run:

```bash
cd server && pytest tests/test_vdjserver_*.py -q
```

## API reference

- Repertoire endpoint: `POST https://vdjserver.org/airr/v1/repertoire`
- AIRR Data Commons API: https://docs.airr-community.org/en/stable/api/adc_api.html
