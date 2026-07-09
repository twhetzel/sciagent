import {
  formatTextBroadTotalsLine,
  isTextBroadEnabled,
  summarizeRetrievalCounts,
} from '../utils/datasetSearchCopy.js'

function formatCount(value) {
  if (value == null || Number.isNaN(Number(value))) return '0'
  return Number(value).toLocaleString()
}

function repositoryLabel(datasetSearch) {
  return datasetSearch?.repository || 'repository'
}

export default function DatasetActionBar({
  datasetSearch,
  loadingMore,
  loadMoreNotice,
  onLoadMore,
}) {
  if (!datasetSearch) return null

  const repository = repositoryLabel(datasetSearch)
  const retrieved = datasetSearch.retrieved_count ?? datasetSearch.candidates?.length ?? 0
  const total = datasetSearch.total_found ?? retrieved
  const retrievableTotal = datasetSearch.retrievable_total
  const batchSize = datasetSearch.max_results || 15
  const canLoadMore =
    datasetSearch.has_more && datasetSearch.load_more_cursor && onLoadMore
  const paginationGap =
    !datasetSearch.has_more &&
    retrievableTotal != null &&
    total > retrievableTotal
  const textBroadEnabled = isTextBroadEnabled(datasetSearch)
  const { supplemental, facetRetrieved, facetTotal, textBroadTotal } =
    summarizeRetrievalCounts(datasetSearch)
  const repositoryTotalsLine = textBroadEnabled
    ? formatTextBroadTotalsLine(facetTotal, textBroadTotal, formatCount)
    : `${formatCount(total)} ${repository} facet hits`

  return (
    <div className="dataset-action-bar" aria-live="polite" aria-busy={loadingMore}>
      <div className="dataset-action-bar-summary">
        <strong>
          {formatCount(retrieved)} ranked
          {textBroadEnabled && !datasetSearch.has_more && supplemental > 0
            ? ` · ${formatCount(facetRetrieved)} facet + ${formatCount(supplemental)} supplemental`
            : null}
          {textBroadEnabled && (datasetSearch.has_more || textBroadTotal != null)
            ? ` · ${repositoryTotalsLine}`
            : null}
          {!textBroadEnabled && datasetSearch.has_more && total > retrieved
            ? ` · ${formatCount(total)} ${repository} facet hits`
            : null}
          {!textBroadEnabled && !datasetSearch.has_more && paginationGap
            ? ` · ${formatCount(total)} reported, ${formatCount(retrievableTotal)} retrievable`
            : !textBroadEnabled && !datasetSearch.has_more && total > retrieved
              ? ` · ${formatCount(total)} ${repository} hits`
              : null}
          {textBroadEnabled && !datasetSearch.has_more && paginationGap
            ? ` · ${formatCount(total)} facet reported, ${formatCount(retrievableTotal)} retrievable`
            : null}
        </strong>
        {textBroadEnabled && datasetSearch.has_more && textBroadTotal != null ? (
          <span className="dataset-action-bar-meta">
            Load more paginates facet strategies first, then{' '}
            <code>text_broad</code> ({formatCount(textBroadTotal)} hits)
          </span>
        ) : textBroadEnabled && datasetSearch.has_more ? (
          <span className="dataset-action-bar-meta">
            Load more may include <code>text_broad</code> free-text supplement
          </span>
        ) : null}
        {datasetSearch.primary_total_found != null &&
        datasetSearch.primary_total_found !== total ? (
          <span className="dataset-action-bar-meta">
            {formatCount(datasetSearch.primary_total_found)} strict matches
          </span>
        ) : null}
      </div>

      <div className="dataset-action-bar-status">
        {loadingMore ? (
          <span className="dataset-action-bar-loading">
            <span className="dataset-action-bar-spinner" aria-hidden="true" />
            Loading more from {repository}…
          </span>
        ) : null}
        {!loadingMore && loadMoreNotice ? (
          <span className="dataset-action-bar-success">
            Added {formatCount(loadMoreNotice.added)} dataset
            {loadMoreNotice.added === 1 ? '' : 's'} · now showing{' '}
            {formatCount(loadMoreNotice.total)} ranked
            {textBroadEnabled && loadMoreNotice.total > total
              ? ' (includes supplemental free-text beyond facet scope)'
              : null}
          </span>
        ) : null}
      </div>

      {canLoadMore ? (
        <button
          type="button"
          className="dataset-action-bar-button"
          onClick={onLoadMore}
          disabled={loadingMore}
        >
          {loadingMore ? 'Loading…' : `Load more (+${batchSize})`}
        </button>
      ) : (
        <span className="dataset-action-bar-done">All retrieved results shown</span>
      )}
    </div>
  )
}
