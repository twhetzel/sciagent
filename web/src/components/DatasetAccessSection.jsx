import { resolveAccessSummary } from '../utils/datasetAccess.js'

function AccessReferenceRow({ reference }) {
  const typeLabel = (reference.access_type || reference.kind || 'unknown').replaceAll('_', ' ')
  return (
    <li className="dataset-access-reference">
      <div className="dataset-access-reference-header">
        <span className="dataset-access-reference-label">{reference.label}</span>
        <span className="dataset-access-reference-kind">{typeLabel}</span>
      </div>
      {reference.notes || reference.description ? (
        <p className="dataset-access-reference-description">
          {reference.notes || reference.description}
        </p>
      ) : null}
      {reference.url ? (
        <a
          className="dataset-access-reference-link"
          href={reference.url}
          target="_blank"
          rel="noreferrer"
        >
          Open reference
        </a>
      ) : null}
    </li>
  )
}

export default function DatasetAccessSection({ candidate, expanded }) {
  if (!expanded) return null

  const summary = resolveAccessSummary(candidate)
  const references = candidate.access_references ?? []
  const hasReferences = references.length > 0

  return (
    <section className="dataset-access-section" aria-label="Access and files">
      <header className="dataset-access-section-header">
        <strong>Access &amp; files</strong>
        <span className="dataset-access-section-note">
          {hasReferences
            ? `${references.length} discovered reference${references.length === 1 ? '' : 's'}`
            : 'Discovery pending'}
        </span>
      </header>

      <p className="dataset-access-section-summary">{summary.text}</p>

      {!hasReferences ? (
        <div className="dataset-access-placeholder">
          <p>
            No access or file references discovered yet. When repository access discovery is
            enabled, this section will list:
          </p>
          <ul>
            <li>Repository study pages and landing URLs</li>
            <li>Supplementary and processed data files</li>
            <li>FTP or API endpoints where direct downloads may be available</li>
            <li>Per-reference notes on authentication requirements</li>
          </ul>
        </div>
      ) : (
        <ul className="dataset-access-reference-list">
          {references.map((reference, index) => (
            <AccessReferenceRow
              key={reference.id || `${reference.label}-${index}`}
              reference={reference}
            />
          ))}
        </ul>
      )}
    </section>
  )
}
