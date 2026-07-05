/** Reference to a file, page, or download endpoint discovered for a dataset. */
export interface AccessReference {
  id?: string
  label: string
  url?: string
  /** Backend field; mirrors kind for repository-specific reference classification. */
  access_type?:
    | 'repository_page'
    | 'direct_download'
    | 'api'
    | 'ftp'
    | 'controlled'
    | 'unknown'
  kind?:
    | 'repository_page'
    | 'supplementary'
    | 'processed_data'
    | 'raw_data'
    | 'metadata'
    | 'ftp'
    | 'other'
  description?: string
  notes?: string
  requires_auth?: boolean
  direct_download?: boolean
}

/** Human-readable access summary for a dataset candidate. */
export interface AccessSummary {
  text?: string
  repository_page_url?: string
  reference_count?: number
  direct_downloads_available?: boolean | null
  auth_may_be_required?: boolean | null
}

/** One dataset entry in an exported access manifest. */
export interface ManifestDatasetEntry {
  accession: string
  repository: string
  title: string
  url: string
  access_summary?: AccessSummary | null
  access_references?: AccessReference[]
}

/** Full manifest export document. */
export interface ManifestExport {
  exported_at: string
  query: string
  sources_searched: string
  export_scope: string
  dataset_count: number
  datasets: ManifestDatasetEntry[]
}

/** Provenance metadata included at the top of manifest exports. */
export interface ManifestProvenance {
  query?: string
  sources_searched?: string
  export_scope?: string
}

/** UI selection state keyed by repository accession (not sent to API). */
export type ManifestSelectionState = Record<string, boolean>
