export const TEXT_BROAD_STRATEGY = 'text_broad'

export function isImmPortTextBroadEnabled(datasetSearch) {
  if (!datasetSearch || datasetSearch.include_text_broad === false) return false
  const repo = datasetSearch.repository || ''
  return repo === 'ImmPort' || repo.includes('ImmPort')
}

export function getTextBroadTotalFound(datasetSearch) {
  if (!isImmPortTextBroadEnabled(datasetSearch)) return null
  const direct = datasetSearch?.text_broad_total_found
  if (typeof direct === 'number' && !Number.isNaN(direct)) {
    return direct
  }
  const row = datasetSearch?.search_strategies?.find(
    (item) => item.strategy === TEXT_BROAD_STRATEGY || item.supplemental,
  )
  if (row?.total_found == null || Number.isNaN(Number(row.total_found))) {
    return null
  }
  return Number(row.total_found)
}

export function countSupplementalCandidates(candidates = []) {
  return candidates.filter(
    (candidate) => candidate.retrieval_strategy === TEXT_BROAD_STRATEGY,
  ).length
}

/** Facet vs supplemental breakdown for ImmPort + text_broad messaging. */
export function summarizeRetrievalCounts(datasetSearch) {
  const candidates = datasetSearch?.candidates || []
  const shown = datasetSearch?.retrieved_count ?? candidates.length ?? 0
  const supplemental = countSupplementalCandidates(candidates)
  const facetRetrieved = Math.max(0, shown - supplemental)
  const facetTotal = datasetSearch?.total_found ?? shown
  const textBroadTotal = getTextBroadTotalFound(datasetSearch)
  return { shown, supplemental, facetRetrieved, facetTotal, textBroadTotal }
}

export function formatTextBroadTotalsLine(facetTotal, textBroadTotal, formatCount) {
  if (textBroadTotal == null) {
    return `${formatCount(facetTotal)} facet hits`
  }
  return `${formatCount(facetTotal)} facet hits · ${formatCount(textBroadTotal)} text_broad hits`
}
