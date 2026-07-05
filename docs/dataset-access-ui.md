# Dataset access UI plan

Lightweight frontend scaffolding for **access details** and **export access manifest**. This document describes the UI shape before backend file/access discovery populates `access_references` for GEO and Expression Atlas.

## Goals

- Present access as **metadata about how to reach data**, not as direct downloading yet.
- Let users review per-dataset access signals, expand detail, and build a manifest for export.
- Keep selection and export entirely client-side until a backend manifest endpoint exists.

## Non-goals (this phase)

- No file downloading or transfer.
- No BioStudies / ArrayExpress integration.
- No new API routes — candidates include `access_summary` and `access_references` after ranking.

## Data model (frontend types)

Extended fields on each `DatasetCandidate` (see `web/src/types/datasetSearch.d.ts`):

| Field | Source | Purpose |
|-------|--------|---------|
| `access_summary` | Backend (optional) | Short text + flags for downloads/auth |
| `access_references` | Backend (optional) | Discovered pages, FTP paths, supplementary files |
| `manifest_selected` | UI only | Whether the candidate is in the export manifest |

`AccessSummary` anticipates:

- `text` — one-line access summary
- `repository_page_url` — canonical study page (falls back to `candidate.url`)
- `reference_count` — optional override; otherwise `access_references.length`
- `direct_downloads_available` — `true` / `false` / `null` (unknown)
- `auth_may_be_required` — `true` / `false` / `null` (unknown)

`AccessReference` anticipates:

- `label`, `url`, `kind`, `description`
- optional `direct_download`, `requires_auth` per reference

## Layout

```
dataset-workspace
├── dataset-discovery-panel        (query context, unchanged)
├── DatasetActionBar               (load more)
├── AccessManifestPanel            (NEW — global manifest bar)
└── dataset-results-list-section
    └── DatasetCard (each)
        ├── … existing match/evidence blocks …
        ├── dataset-access-summary   (NEW — compact strip)
        ├── dataset-access-actions   (NEW — buttons/links)
        └── DatasetAccessSection     (NEW — expandable “Access & files”)
```

The manifest panel sits between the action bar and the ranked list so selection count and export actions stay visible while scrolling results.

## Per-card UI

### Access summary strip

Shows when a card renders (placeholder copy when discovery has not run):

- Access summary text
- Repository page link (uses `access_summary.repository_page_url` or `candidate.url`)
- Count of discovered access/file references
- Direct downloads: Yes / No / Unknown
- Authentication: May be required / Not indicated / Unknown

### Actions

| Control | Behavior |
|---------|----------|
| **View access details** | Toggles expanded “Access & files” section on the card |
| **Open repository page** | Opens repository URL in a new tab |
| **Add to manifest** / **Remove from manifest** | Toggles `manifest_selected` for that accession |

Selected cards get `.dataset-card--manifest-selected` styling.

### Access & files (expanded)

- Header: “Access & files”
- When `access_references` is empty: placeholder explaining discovery is pending and listing what will appear (repository links, supplementary files, processed/raw data references).
- When populated (future): list each reference with label, kind badge, URL, and per-reference flags.

## Manifest panel

Global bar (`AccessManifestPanel`):

- **Selected datasets** count
- **Export manifest JSON** — downloads `access-manifest.json`
- **Export manifest Markdown** — downloads `access-manifest.md`

Export includes provenance at the top of JSON/Markdown (`query`, `sources_searched`, `export_scope`, `dataset_count`) plus per-dataset access fields for selected candidates only.

Selection state lives in `App.jsx` as a `Set` of accessions; it resets on a new search query.

## Backend handoff

Access discovery runs after ranking in `server/domain/dataset_access_discovery.py` and populates each `DatasetCandidate` with `access_summary` and `access_references` for GEO and Expression Atlas.

Optional later: persist manifest server-side or add “refresh access details” per accession.

## Files

| Path | Role |
|------|------|
| `web/src/types/datasetAccess.d.ts` | Access + manifest types |
| `web/src/types/datasetSearch.d.ts` | Extended candidate/search types |
| `server/domain/dataset_access_discovery.py` | GEO/GXA access discovery and candidate enrichment |
| `web/src/utils/datasetAccess.js` | Summary resolution, manifest export helpers |
| `web/src/components/DatasetAccessSection.jsx` | Expandable access detail block |
| `web/src/components/AccessManifestPanel.jsx` | Global manifest bar + export |
| `web/src/components/DatasetResultsPanel.jsx` | Card integration |
| `web/src/App.jsx` | Manifest selection state |
| `web/src/App.css` | Access + manifest styles |
