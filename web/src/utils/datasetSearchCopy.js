export const TEXT_BROAD_STRATEGY = 'text_broad'

export function isImmPortTextBroadEnabled(datasetSearch) {
  if (!datasetSearch || datasetSearch.include_text_broad === false) return false
  const repo = datasetSearch.repository || ''
  return repo === 'ImmPort' || repo.includes('ImmPort')
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
  return { shown, supplemental, facetRetrieved, facetTotal }
}
