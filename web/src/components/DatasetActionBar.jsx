function formatCount(value) {
  if (value == null || Number.isNaN(Number(value))) return '0'
  return Number(value).toLocaleString()
}

export default function DatasetActionBar({
  datasetSearch,
  loadingMore,
  loadMoreNotice,
  onLoadMore,
}) {
  if (!datasetSearch) return null

  const retrieved = datasetSearch.retrieved_count ?? datasetSearch.candidates?.length ?? 0
  const total = datasetSearch.total_found ?? retrieved
  const batchSize = datasetSearch.max_results || 15
  const canLoadMore = datasetSearch.has_more && onLoadMore

  return (
    <div className="dataset-action-bar" aria-live="polite" aria-busy={loadingMore}>
      <div className="dataset-action-bar-summary">
        <strong>
          {formatCount(retrieved)} ranked
          {total > retrieved ? ` · ${formatCount(total)} GEO hits` : ''}
        </strong>
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
            Loading more from GEO…
          </span>
        ) : null}
        {!loadingMore && loadMoreNotice ? (
          <span className="dataset-action-bar-success">
            Added {formatCount(loadMoreNotice.added)} dataset
            {loadMoreNotice.added === 1 ? '' : 's'} · now showing{' '}
            {formatCount(loadMoreNotice.total)}
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
