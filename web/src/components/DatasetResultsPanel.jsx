function ConceptChip({ mapping, variant = 'matched' }) {
  return (
    <span className={`concept-chip concept-chip--${variant}`} title={mapping.curie}>
      {mapping.slot}: {mapping.label}
    </span>
  )
}

function MatchStatusBadge({ status }) {
  if (!status) return null
  return <span className={`dataset-match-status dataset-match-status--${status}`}>{status}</span>
}

function EvidenceList({ evidence }) {
  if (!evidence?.length) return null
  return (
    <div className="dataset-evidence-block">
      <strong>Evidence</strong>
      <ul className="dataset-evidence">
        {evidence.map((item, index) => (
          <li key={`${item.field}-${index}`}>
            <span className="dataset-evidence-field">{item.field}</span>
            <span className="dataset-evidence-text">{item.text}</span>
            {item.matched_concepts?.length > 0 && (
              <span className="dataset-evidence-concepts">
                matched: {item.matched_concepts.join(', ')}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

function requestedAssay(candidate) {
  return candidate.requested_concepts?.find((mapping) => mapping.slot === 'assay')?.label
}

function DatasetCard({ candidate, rank }) {
  const requestedAssayLabel = requestedAssay(candidate)

  return (
    <article className={`dataset-card dataset-card--${candidate.match_status || 'partial'}`}>
      <header className="dataset-card-header">
        <div>
          <span className="dataset-rank">#{rank}</span>
          <a
            className="dataset-accession"
            href={candidate.url}
            target="_blank"
            rel="noreferrer"
          >
            {candidate.accession}
          </a>
          <span className="dataset-repository">{candidate.repository}</span>
          <MatchStatusBadge status={candidate.match_status} />
        </div>
        <span className="dataset-score">Score {candidate.score.toFixed(2)}</span>
      </header>

      <h3 className="dataset-title">{candidate.title}</h3>

      {candidate.description && (
        <p className="dataset-description">{candidate.description}</p>
      )}

      <div className="dataset-meta">
        {requestedAssayLabel && <span>Requested: {requestedAssayLabel}</span>}
        <span>
          Observed assay: {candidate.observed_assay || 'unknown'}
        </span>
        {candidate.observed_organism && (
          <span>Observed organism: {candidate.observed_organism}</span>
        )}
        {candidate.observed_disease && (
          <span>Observed disease: {candidate.observed_disease}</span>
        )}
        {candidate.observed_tissue && (
          <span>Observed tissue: {candidate.observed_tissue}</span>
        )}
        {candidate.sample_count != null && (
          <span>Samples: {candidate.sample_count}</span>
        )}
      </div>

      {candidate.requested_concepts?.length > 0 && (
        <div className="dataset-requested">
          <strong>Requested concepts</strong>
          <div className="dataset-concepts">
            {candidate.requested_concepts.map((mapping) => (
              <ConceptChip
                key={`${candidate.accession}-req-${mapping.curie}`}
                mapping={mapping}
                variant="requested"
              />
            ))}
          </div>
        </div>
      )}

      {candidate.matched_concepts?.length > 0 && (
        <div className="dataset-supported">
          <strong>Supported by evidence</strong>
          <div className="dataset-concepts">
            {candidate.matched_concepts.map((mapping) => (
              <ConceptChip
                key={`${candidate.accession}-match-${mapping.curie}`}
                mapping={mapping}
                variant="matched"
              />
            ))}
          </div>
        </div>
      )}

      {candidate.why_matched?.length > 0 && (
        <div className="dataset-why">
          <strong>Why this matched</strong>
          <ul>
            {candidate.why_matched.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      )}

      {(candidate.why_partial?.length > 0 || candidate.conflicting_assays?.length > 0) && (
        <div className="dataset-partial">
          <strong>Why partial or conflicting</strong>
          <ul>
            {candidate.why_partial?.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
            {candidate.conflicting_assays?.map((assay) => (
              <li key={assay}>Conflicting assay detected in metadata: {assay}</li>
            ))}
          </ul>
        </div>
      )}

      <EvidenceList evidence={candidate.evidence_snippets} />
    </article>
  )
}

export default function DatasetResultsPanel({ datasetSearch }) {
  if (!datasetSearch) return null

  const { interpreted_query: interpreted, concept_mappings: mappings, candidates } =
    datasetSearch

  return (
    <section className="dataset-results">
      <header className="dataset-results-header">
        <h2>Dataset discovery</h2>
        <p>
          Ontology-grounded search via {datasetSearch.source || 'GEO'} —{' '}
          {datasetSearch.total_found ?? candidates?.length ?? 0} total hits
        </p>
      </header>

      {interpreted && (
        <div className="dataset-interpreted">
          <strong>Requested facets</strong>
          <div className="dataset-interpreted-slots">
            {interpreted.disease && <span>disease: {interpreted.disease}</span>}
            {interpreted.tissue && <span>tissue: {interpreted.tissue}</span>}
            {interpreted.assay && <span>assay: {interpreted.assay}</span>}
            {interpreted.organism && <span>organism: {interpreted.organism}</span>}
          </div>
        </div>
      )}

      {mappings?.length > 0 && (
        <div className="dataset-grounded">
          <strong>Grounded query concepts</strong>
          <div className="dataset-concepts">
            {mappings.map((mapping) => (
              <ConceptChip key={mapping.curie} mapping={mapping} variant="requested" />
            ))}
          </div>
        </div>
      )}

      <div className="dataset-list">
        {(candidates || []).map((candidate, index) => (
          <DatasetCard key={candidate.accession} candidate={candidate} rank={index + 1} />
        ))}
      </div>

      {(!candidates || candidates.length === 0) && (
        <p className="dataset-empty">No ranked dataset candidates returned.</p>
      )}
    </section>
  )
}
