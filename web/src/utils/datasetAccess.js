/** @typedef {import('../types/datasetAccess.d.ts').AccessReference} AccessReference */
/** @typedef {import('../types/datasetAccess.d.ts').AccessSummary} AccessSummary */
/** @typedef {import('../types/datasetAccess.d.ts').ManifestExport} ManifestExport */
/** @typedef {import('../types/datasetAccess.d.ts').ManifestProvenance} ManifestProvenance */
/** @typedef {import('../types/datasetSearch.d.ts').DatasetCandidate} DatasetCandidate */
/** @typedef {import('../types/datasetSearch.d.ts').DatasetSearchResult} DatasetSearchResult */

const PENDING_SUMMARY_TEXT =
  'Access details pending discovery. File and download references will appear here once repository access discovery runs.'

/**
 * @param {boolean | null | undefined} value
 * @returns {'yes' | 'no' | 'unknown'}
 */
export function triStateLabel(value) {
  if (value === true) return 'yes'
  if (value === false) return 'no'
  return 'unknown'
}

/** @param {'yes' | 'no' | 'unknown'} state */
export function formatTriState(state, labels) {
  return labels[state] ?? labels.unknown
}

/**
 * Resolve display access summary for a candidate, with scaffolding defaults.
 * @param {DatasetCandidate} candidate
 * @returns {Required<Pick<AccessSummary, 'text' | 'repository_page_url'>> & AccessSummary}
 */
export function resolveAccessSummary(candidate) {
  const summary = candidate.access_summary ?? {}
  const references = candidate.access_references ?? []
  const hasBackendSummary = Boolean(candidate.access_summary)
  const referenceCount =
    summary.reference_count ?? references.length ?? 0

  return {
    text: hasBackendSummary
      ? summary.text || PENDING_SUMMARY_TEXT
      : PENDING_SUMMARY_TEXT,
    repository_page_url: summary.repository_page_url || candidate.url || '',
    reference_count: referenceCount,
    direct_downloads_available: hasBackendSummary
      ? summary.direct_downloads_available ??
        (references.some((ref) => ref.direct_download || ref.access_type === 'direct_download')
          ? true
          : null)
      : references.some((ref) => ref.direct_download || ref.access_type === 'direct_download')
        ? true
        : null,
    auth_may_be_required: hasBackendSummary
      ? summary.auth_may_be_required ??
        (references.some((ref) => ref.requires_auth) ? true : null)
      : references.some((ref) => ref.requires_auth)
        ? true
        : null,
  }
}

/** @param {DatasetCandidate} candidate */
export function getAccessReferenceCount(candidate) {
  return resolveAccessSummary(candidate).reference_count ?? 0
}

/**
 * @param {DatasetCandidate[]} candidates
 * @param {Set<string>} selectedAccessions
 */
export function selectedManifestCandidates(candidates, selectedAccessions) {
  if (!candidates?.length || !selectedAccessions?.size) return []
  return candidates.filter((candidate) => selectedAccessions.has(candidate.accession))
}

/**
 * @param {DatasetSearchResult | null | undefined} datasetSearch
 */
export function formatSourcesSearched(datasetSearch) {
  const repository = datasetSearch?.repository?.trim()
  if (!repository) return 'Unknown'

  if (repository.includes('+')) {
    return repository
      .split('+')
      .map((source) => source.trim())
      .filter(Boolean)
      .join(', ')
  }

  const fromStrategies = [
    ...new Set(
      (datasetSearch.search_strategies ?? [])
        .map((strategy) => strategy.repository)
        .filter(Boolean),
    ),
  ]
  if (fromStrategies.length > 1) {
    return fromStrategies.join(', ')
  }

  return repository
}

/**
 * @param {{
 *   selectedAccessions?: Set<string>
 *   candidates?: DatasetCandidate[]
 *   exportMode?: 'selected' | 'top' | 'all'
 *   topN?: number
 * }} options
 */
export function resolveManifestExportScope({
  selectedAccessions,
  candidates = [],
  exportMode = 'selected',
  topN,
}) {
  if (exportMode === 'top' && topN) {
    return `top ${topN} results`
  }
  if (exportMode === 'all') {
    return 'all retrieved results'
  }
  if (selectedAccessions?.size) {
    return 'selected datasets'
  }
  if (exportMode === 'top' && candidates.length) {
    return `top ${candidates.length} results`
  }
  if (candidates.length) {
    return 'all retrieved results'
  }
  return 'selected datasets'
}

/**
 * @param {DatasetSearchResult | null | undefined} datasetSearch
 * @param {Set<string>} selectedAccessions
 * @param {DatasetCandidate[]} candidates
 * @param {ManifestProvenance} [overrides]
 */
export function buildManifestProvenance(
  datasetSearch,
  selectedAccessions,
  candidates,
  overrides = {},
) {
  return {
    query: overrides.query ?? datasetSearch?.query ?? '',
    sources_searched:
      overrides.sources_searched ?? formatSourcesSearched(datasetSearch),
    export_scope:
      overrides.export_scope ??
      resolveManifestExportScope({
        selectedAccessions,
        candidates,
        exportMode: 'selected',
      }),
  }
}

/**
 * @param {DatasetCandidate[]} candidates
 * @param {Set<string>} selectedAccessions
 * @param {ManifestProvenance & { datasetSearch?: DatasetSearchResult | null }} [options]
 * @returns {ManifestExport}
 */
export function buildManifestExport(candidates, selectedAccessions, options = {}) {
  const { datasetSearch, ...overrides } = options
  const selected = selectedManifestCandidates(candidates, selectedAccessions)
  const header = buildManifestProvenance(
    datasetSearch,
    selectedAccessions,
    candidates,
    overrides,
  )
  return {
    exported_at: new Date().toISOString(),
    query: header.query,
    sources_searched: header.sources_searched,
    export_scope: header.export_scope,
    dataset_count: selected.length,
    datasets: selected.map((candidate) => ({
      accession: candidate.accession,
      repository: candidate.repository,
      title: candidate.title,
      url: candidate.url || resolveAccessSummary(candidate).repository_page_url,
      access_summary: candidate.access_summary ?? resolveAccessSummary(candidate),
      access_references: candidate.access_references ?? [],
    })),
  }
}

/**
 * @param {DatasetCandidate[]} candidates
 * @param {Set<string>} selectedAccessions
 * @param {ManifestProvenance & { datasetSearch?: DatasetSearchResult | null }} [options]
 */
export function buildManifestMarkdown(candidates, selectedAccessions, options = {}) {
  const manifest = buildManifestExport(candidates, selectedAccessions, options)
  const lines = [
    '# Dataset access manifest',
    '',
    `Exported: ${manifest.exported_at}`,
    `Query: ${manifest.query || 'Unknown'}`,
    `Sources searched: ${manifest.sources_searched}`,
    `Export scope: ${manifest.export_scope}`,
    `Datasets: ${manifest.dataset_count}`,
    '',
  ]

  if (!manifest.datasets.length) {
    lines.push('_No datasets selected._')
    return lines.join('\n')
  }

  for (const entry of manifest.datasets) {
    const summary = entry.access_summary ?? {}
    const refs = entry.access_references ?? []
    lines.push(`## ${entry.accession} (${entry.repository})`)
    lines.push('')
    lines.push(`- **Title:** ${entry.title}`)
    if (entry.url) lines.push(`- **Repository page:** ${entry.url}`)
    if (summary.text) lines.push(`- **Access summary:** ${summary.text}`)
    lines.push(
      `- **Direct downloads:** ${formatTriState(triStateLabel(summary.direct_downloads_available), {
        yes: 'Available',
        no: 'Not indicated',
        unknown: 'Unknown',
      })}`,
    )
    lines.push(
      `- **Authentication:** ${formatTriState(triStateLabel(summary.auth_may_be_required), {
        yes: 'May be required',
        no: 'Not indicated',
        unknown: 'Unknown',
      })}`,
    )
    lines.push(`- **Access references:** ${refs.length}`)
    if (refs.length) {
      lines.push('')
      for (const ref of refs) {
        const kind = ref.kind ? ` (${ref.kind})` : ''
        lines.push(`- ${ref.label}${kind}${ref.url ? `: ${ref.url}` : ''}`)
      }
    }
    lines.push('')
  }

  return lines.join('\n')
}

/**
 * @param {string} content
 * @param {string} filename
 * @param {string} mimeType
 */
export function downloadTextFile(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}
