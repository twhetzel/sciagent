import { useState } from 'react'

function ConceptChip({ mapping, variant = 'matched' }) {
  const title = mapping.explanation
    ? `${mapping.curie} — ${mapping.explanation}`
    : `${mapping.curie} (${mapping.source || 'unknown'}, ${mapping.match_type || 'unknown'})`
  return (
    <span className={`concept-chip concept-chip--${variant}`} title={title}>
      {mapping.slot}: {mapping.label}
      {mapping.source ? <span className="concept-chip-source"> · {mapping.source}</span> : null}
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

function WarningList({ warnings, title }) {
  if (!warnings?.length) return null
  return (
    <div className="dataset-warnings">
      <strong>{title}</strong>
      <ul>
        {warnings.map((warning) => (
          <li key={warning}>{warning}</li>
        ))}
      </ul>
    </div>
  )
}

function requestedAssay(candidate) {
  return candidate.requested_concepts?.find((mapping) => mapping.slot === 'assay')?.label
}

function ScoreBreakdownPanel({ breakdown }) {
  const [expanded, setExpanded] = useState(false)
  if (!breakdown) return null

  function renderSlot(label, slot) {
    const status = slot.present ? 'present' : 'absent'
    const fields = slot.fields?.length ? slot.fields.join(', ') : '—'
    const terms = slot.matched_terms?.length ? slot.matched_terms.join(', ') : '—'
    return (
      <div className="score-breakdown-row" key={label}>
        <span className="score-breakdown-slot">{label}</span>
        <span className={`score-breakdown-status score-breakdown-status--${status}`}>{status}</span>
        <span className="score-breakdown-detail">fields: {fields}</span>
        <span className="score-breakdown-detail">terms: {terms}</span>
        {label === 'tissue' && slot.evidence_type ? (
          <span className="score-breakdown-detail">type: {slot.evidence_type}</span>
        ) : null}
      </div>
    )
  }

  return (
    <div className="score-breakdown">
      <button
        type="button"
        className="score-breakdown-toggle"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
      >
        Score breakdown (debug)
      </button>
      {expanded && (
        <div className="score-breakdown-body">
          <div className="score-breakdown-summary">
            <span>Score {breakdown.final_score?.toFixed(3)}</span>
            <span>Status {breakdown.match_status}</span>
            <span>Coverage {breakdown.evidence_coverage?.toFixed(3)}</span>
            {breakdown.retrieval_strategy ? (
              <span>Strategy {breakdown.retrieval_strategy}</span>
            ) : null}
            <span>Warnings {breakdown.warnings_count}</span>
            <span>Conflicts {breakdown.evidence_conflicts_count}</span>
          </div>
          {renderSlot('disease', breakdown.disease)}
          {renderSlot('tissue', breakdown.tissue)}
          {renderSlot('assay', breakdown.assay)}
          {renderSlot('organism', breakdown.organism)}
        </div>
      )}
    </div>
  )
}

function DatasetCard({ candidate, rank }) {
  const requestedAssayLabel = requestedAssay(candidate)
  const assayMatched = candidate.matched_concepts?.some((mapping) => mapping.slot === 'assay')

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
        <span>Observed assay: {candidate.observed_assay || 'unknown'}</span>
        {assayMatched && requestedAssayLabel && (
          <span>Assay evidence: {requestedAssayLabel} supported in metadata</span>
        )}
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
        {candidate.retrieval_strategy && (
          <span>
            Retrieved via {candidate.retrieval_strategy}
            {candidate.retrieval_search_term ? (
              <> · <code>{candidate.retrieval_search_term}</code></>
            ) : null}
          </span>
        )}
      </div>

      <WarningList warnings={candidate.metadata_warnings} title="Metadata warnings" />

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

      {candidate.why_partial?.length > 0 && (
        <div className="dataset-partial">
          <strong>Why partial</strong>
          <ul>
            {candidate.why_partial.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      )}

      <EvidenceList evidence={candidate.evidence_snippets} />
      <ScoreBreakdownPanel breakdown={candidate.score_breakdown} />
    </article>
  )
}

function AgentContextPanel({ agentContext }) {
  const [format, setFormat] = useState('markdown')
  const [copied, setCopied] = useState(false)
  const [expanded, setExpanded] = useState(false)

  if (!agentContext) return null

  const content =
    format === 'markdown'
      ? agentContext.markdown
      : JSON.stringify(agentContext.json, null, 2)

  async function handleCopy() {
    if (!content) return
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="dataset-agent-context">
      <div className="dataset-agent-context-header">
        <strong>Agent context export</strong>
        <div className="dataset-agent-context-actions">
          <div className="dataset-agent-context-toggle" role="tablist" aria-label="Context format">
            <button
              type="button"
              role="tab"
              aria-selected={format === 'markdown'}
              className={format === 'markdown' ? 'is-active' : ''}
              onClick={() => setFormat('markdown')}
            >
              Markdown
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={format === 'json'}
              className={format === 'json' ? 'is-active' : ''}
              onClick={() => setFormat('json')}
            >
              JSON
            </button>
          </div>
          <button type="button" className="dataset-agent-context-copy" onClick={handleCopy}>
            {copied ? 'Copied' : 'Copy'}
          </button>
          <button
            type="button"
            className="dataset-agent-context-view"
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? 'Hide' : 'View'}
          </button>
        </div>
      </div>
      <p className="dataset-agent-context-note">
        Structured context for downstream agents — includes query facets, grounded concepts,
        evidence, warnings, and cautions.
      </p>
      {expanded && (
        <pre className="dataset-agent-context-body">{content}</pre>
      )}
    </div>
  )
}

export default function DatasetResultsPanel({ datasetSearch }) {
  if (!datasetSearch) return null

  const {
    interpreted_query: interpreted,
    concept_mappings: mappings,
    candidates,
    agent_context: agentContext,
  } = datasetSearch

  return (
    <section className="dataset-results">
      <header className="dataset-results-header">
        <h2>Dataset discovery</h2>
        <p>
          Ontology-grounded search via {datasetSearch.source || 'GEO'}
          {datasetSearch.repository ? ` (${datasetSearch.repository})` : ''} —{' '}
          {datasetSearch.total_found ?? candidates?.length ?? 0} total hits
          {datasetSearch.search_term ? (
            <>
              {' '}
              · primary query: <code>{datasetSearch.search_term}</code>
            </>
          ) : null}
          {datasetSearch.search_strategies?.length > 0 ? (
            <>
              {' '}
              · {datasetSearch.search_strategies.length} search strategies
            </>
          ) : null}
        </p>
      </header>

      <AgentContextPanel agentContext={agentContext} />

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
