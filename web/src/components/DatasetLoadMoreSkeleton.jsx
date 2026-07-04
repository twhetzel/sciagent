export default function DatasetLoadMoreSkeleton({ count = 2 }) {
  return (
    <div className="dataset-load-more-skeleton" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <div className="dataset-load-more-skeleton-card" key={index}>
          <div className="dataset-skeleton-line dataset-skeleton-line--short" />
          <div className="dataset-skeleton-line dataset-skeleton-line--title" />
          <div className="dataset-skeleton-line" />
          <div className="dataset-skeleton-line dataset-skeleton-line--medium" />
        </div>
      ))}
    </div>
  )
}
