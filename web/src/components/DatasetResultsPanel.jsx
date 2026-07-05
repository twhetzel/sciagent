import { useState } from 'react'
import DatasetActionBar from './DatasetActionBar.jsx'
import DatasetLoadMoreSkeleton from './DatasetLoadMoreSkeleton.jsx'
import { FacetStatusInfoTooltip, FacetStatusLabelTooltip } from './FacetStatusTooltip.jsx'
import {
  buildFacetSummary,
  deriveFacetStatus,
  FACET_STATUS_ORDER,
  facetLabel,
  facetStatusLabel,
  requestedFacetSlots,
} from '../utils/facetCoverage.js'

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

function formatMatchStatus(status) {
  if (!status) return status
  return status.replaceAll('_', ' ')
}

function formatCount(value) {
  if (value == null || Number.isNaN(Number(value))) return '0'
  return Number(value).toLocaleString()
}

function repositoryLabel(datasetSearch) {
  return datasetSearch?.repository || 'repository'
}

function maxResultsEnvVar(datasetSearch) {
  const repo = repositoryLabel(datasetSearch)
  if (repo.includes('+')) return 'GEO_MAX_RESULTS and EXPRESSION_ATLAS_MAX_RESULTS'
  if (repo === 'GEO') return 'GEO_MAX_RESULTS'
  return 'EXPRESSION_ATLAS_MAX_RESULTS'
}

function HitSummaryBanner({ datasetSearch, candidateCount, loadingMore }) {
  const repository = repositoryLabel(datasetSearch)
  const totalFound = datasetSearch.total_found ?? candidateCount
  const primaryTotalFound = datasetSearch.primary_total_found
  const maxResults = datasetSearch.max_results
  const shown = datasetSearch.retrieved_count ?? candidateCount ?? 0
  const hasMore = totalFound > shown
  const strictDiffers =
    primaryTotalFound != null && primaryTotalFound !== totalFound

  return (
    <div
      className={`dataset-results-hit-summary${hasMore ? ' dataset-results-hit-summary--truncated' : ''}${loadingMore ? ' dataset-results-hit-summary--loading' : ''}`}
      role="status"
    >
      <strong>
        {loadingMore
          ? `Loading more… (${formatCount(shown)} ranked so far)`
          : hasMore
            ? `Showing ${formatCount(shown)} of ${formatCount(totalFound)} ${repository} hits`
            : `Showing ${formatCount(shown)} ranked ${shown === 1 ? 'hit' : 'hits'}`}
      </strong>
      <span>
        {hasMore ? (
          <>
            Retrieved and ranked the top matches by evidence coverage
            {strictDiffers ? (
              <>
                {' '}
                ({formatCount(primaryTotalFound)} match the primary strict query)
              </>
            ) : null}
            {maxResults ? (
              <>
                {' '}
                · limit <code>{formatCount(maxResults)}</code>
                {' '}
                via <code>{maxResultsEnvVar(datasetSearch)}</code>
              </>
            ) : null}
            .
          </>
        ) : (
          <>
            All matching records retrieved from {repository} were ranked below.
            {strictDiffers ? (
              <>
                {' '}
                Primary strict query: {formatCount(primaryTotalFound)} hits.
              </>
            ) : null}
          </>
        )}
      </span>
    </div>
  )
}

function MatchStatusBadge({ status }) {
  if (!status) return null
  return (
    <span className={`dataset-match-status dataset-match-status--${status}`}>
      {formatMatchStatus(status)}
    </span>
  )
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

function FacetCoverageSummary({ candidates, mappings }) {
  const { rows, total } = buildFacetSummary(candidates, mappings)

  if (!rows.length) return null

  return (
    <div className="facet-coverage-matrix">
      <div className="facet-coverage-matrix-header">
        <strong>Query match summary</strong>
        <span className="facet-coverage-matrix-note">
          Evidence counts across {formatCount(total)} ranked{' '}
          {total === 1 ? 'dataset' : 'datasets'}
        </span>
      </div>
      <table className="facet-coverage-table facet-coverage-table--summary">
        <thead>
          <tr>
            <th scope="col" className="facet-coverage-concept-header">
              Grounded concept
            </th>
            {FACET_STATUS_ORDER.map((status) => (
              <th
                key={status}
                scope="col"
                className={`facet-coverage-status-header facet-coverage-status-header--${status}`}
              >
                <FacetStatusLabelTooltip status={status} />
              </th>
            ))}
            <th scope="col" className="facet-coverage-distribution-header">
              Distribution
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.slot}>
              <th scope="row" className="facet-coverage-concept-label">
                <span className="facet-coverage-concept-slot">{row.slot}</span>
                <span className="facet-coverage-concept-name" title={row.curie || row.label}>
                  {row.label}
                </span>
              </th>
              {FACET_STATUS_ORDER.map((status) => {
                const count = row.counts[status]
                return (
                  <td
                    key={`${row.slot}-${status}`}
                    className={`facet-coverage-count facet-coverage-count--${status}${count ? '' : ' facet-coverage-count--zero'}`}
                  >
                    {formatCount(count)}
                  </td>
                )
              })}
              <td className="facet-coverage-distribution">
                <div
                  className="facet-coverage-stack"
                  role="img"
                  aria-label={`${row.label} evidence distribution across ${formatCount(total)} datasets`}
                >
                  {FACET_STATUS_ORDER.map((status) =>
                    row.counts[status] > 0 ? (
                      <span
                        key={`${row.slot}-bar-${status}`}
                        className={`facet-coverage-stack-segment facet-coverage-stack-segment--${status}`}
                        style={{ flexGrow: row.counts[status] }}
                        title={`${formatCount(row.counts[status])} ${facetStatusLabel(status).toLowerCase()}`}
                      />
                    ) : null,
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FacetCoverageStrip({ candidate, mappings }) {
  const requestedSlots = requestedFacetSlots(
    mappings?.length ? mappings : candidate.requested_concepts,
  )
  const requestedSet = new Set(requestedSlots)

  if (!requestedSlots.length || !candidate.score_breakdown) return null

  return (
    <div className="facet-coverage-strip" aria-label="Facet evidence coverage">
      {requestedSlots.map((slot) => {
        const status = deriveFacetStatus(slot, candidate.score_breakdown, requestedSet)
        const label = facetLabel(slot, mappings?.length ? mappings : candidate.requested_concepts)
        return (
          <FacetStatusInfoTooltip
            key={slot}
            status={status}
            detail={`${label}: ${facetStatusLabel(status)}`}
            className={`facet-coverage-strip-item facet-coverage-strip-item--${status}`}
          >
            <span className="facet-coverage-strip-trigger">
              <span className="facet-coverage-strip-bar" aria-hidden="true" />
              <span className="facet-coverage-strip-label">{slot}</span>
            </span>
          </FacetStatusInfoTooltip>
        )
      })}
    </div>
  )
}

function ScoreBreakdownPanel({ breakdown }) {
  const [expanded, setExpanded] = useState(false)
  if (!breakdown) return null

  function renderSlot(label, slot, extraDetail) {
    const status = slot.present ? 'present' : 'absent'
    const fields = slot.fields?.length ? slot.fields.join(', ') : '—'
    const terms = slot.matched_terms?.length ? slot.matched_terms.join(', ') : '—'
    return (
      <div className="score-breakdown-row" key={label}>
        <span className="score-breakdown-slot">{label}</span>
        <span className={`score-breakdown-status score-breakdown-status--${status}`}>{status}</span>
        <span className="score-breakdown-detail">fields: {fields}</span>
        <span className="score-breakdown-detail">terms: {terms}</span>
        {extraDetail ? (
          <span className="score-breakdown-detail">{extraDetail}</span>
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
            <span>
              Display rank {(breakdown.display_rank_score ?? breakdown.evidence_score)?.toFixed(3)}
            </span>
            <span>Evidence {breakdown.evidence_score?.toFixed(3)}</span>
            <span>Tier {breakdown.rank_tier ?? breakdown.match_tier}</span>
            {breakdown.partial_assay_subtype ? (
              <span>Subtype {breakdown.partial_assay_subtype.replaceAll('_', ' ')}</span>
            ) : null}
            <span>Base {breakdown.base_score?.toFixed(3)}</span>
            <span>
              Adjust {breakdown.quality_adjustment >= 0 ? '+' : ''}
              {breakdown.quality_adjustment?.toFixed(3)}
            </span>
            <span>Status {formatMatchStatus(breakdown.match_status)}</span>
            <span>Coverage {breakdown.evidence_coverage?.toFixed(3)}</span>
            {breakdown.retrieval_strategy ? (
              <span>Strategy {breakdown.retrieval_strategy}</span>
            ) : null}
            <span>Warnings {breakdown.warnings_count}</span>
            <span>Conflicts {breakdown.evidence_conflicts_count}</span>
          </div>
          {renderSlot('disease', breakdown.disease)}
          {renderSlot(
            'tissue',
            breakdown.tissue,
            breakdown.tissue?.evidence_type
              ? `tissue type: ${breakdown.tissue.evidence_type.replaceAll('_', ' ')}`
              : null,
          )}
          {renderSlot('assay', breakdown.assay)}
          {renderSlot(
            'organism',
            breakdown.organism,
            breakdown.organism?.evidence_source
              ? `source: ${breakdown.organism.evidence_source}`
              : null,
          )}
          {breakdown.match_tier_note ? (
            <p className="score-breakdown-tier-note">{breakdown.match_tier_note}</p>
          ) : null}
          {breakdown.warnings?.length > 0 && (
            <div className="score-breakdown-warnings">
              <strong>Warnings</strong>
              <ul>
                {breakdown.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}
          {breakdown.evidence_conflicts?.length > 0 && (
            <div className="score-breakdown-conflicts">
              <strong>Evidence conflicts</strong>
              <ul>
                {breakdown.evidence_conflicts.map((conflict) => (
                  <li key={conflict}>{conflict}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function DatasetCard({ candidate, rank, isNew, conceptMappings }) {
  const requestedAssayLabel = requestedAssay(candidate)
  const assayMatched = candidate.matched_concepts?.some((mapping) => mapping.slot === 'assay')

  return (
    <article
      className={`dataset-card dataset-card--${candidate.match_status || 'partial'}${isNew ? ' dataset-card--new' : ''}`}
      data-candidate-rank={rank}
    >
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
        <span className="dataset-score">Rank {candidate.score.toFixed(2)}</span>
      </header>

      <h3 className="dataset-title">{candidate.title}</h3>

      {candidate.description && (
        <p className="dataset-description">{candidate.description}</p>
      )}

      <FacetCoverageStrip candidate={candidate} mappings={conceptMappings} />

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

function AssistantSummary({ messages, loading }) {
  const latestUser = [...(messages || [])].reverse().find((msg) => msg.role === 'user')
  const latestAssistant = [...(messages || [])].reverse().find((msg) => msg.role === 'assistant')

  if (!latestUser && !loading) return null

  return (
    <div className="dataset-assistant-summary">
      <strong>Agent summary</strong>
      {latestUser ? (
        <p className="dataset-assistant-query">
          <span className="dataset-assistant-label">Query</span> {latestUser.content}
        </p>
      ) : null}
      {loading ? (
        <p className="dataset-assistant-response loading-pulse">Searching databases…</p>
      ) : latestAssistant ? (
        <p className="dataset-assistant-response">{latestAssistant.content}</p>
      ) : null}
    </div>
  )
}

export default function DatasetResultsPanel({
  datasetSearch,
  loadingMore,
  newFromRank,
  listScrollRef,
  messages,
  loading,
  loadMoreNotice,
  onLoadMore,
}) {
  if (!datasetSearch) return null

  const {
    interpreted_query: interpreted,
    concept_mappings: mappings,
    candidates,
    agent_context: agentContext,
  } = datasetSearch
  const candidateCount = datasetSearch.retrieved_count ?? candidates?.length ?? 0

  return (
    <>
      <section className="dataset-discovery-panel" aria-label="Dataset discovery context">
        <header className="dataset-results-header">
          <h2>Dataset discovery</h2>
          <p>
            Ontology-grounded search via {datasetSearch.source || repositoryLabel(datasetSearch)}
            {datasetSearch.repository ? ` (${datasetSearch.repository})` : ''}
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

        <AssistantSummary messages={messages} loading={loading} />

        <HitSummaryBanner
          datasetSearch={datasetSearch}
          candidateCount={candidateCount}
          loadingMore={loadingMore}
        />

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

        <FacetCoverageSummary candidates={candidates} mappings={mappings} />

        <AgentContextPanel agentContext={agentContext} />
      </section>

      <DatasetActionBar
        datasetSearch={datasetSearch}
        loadingMore={loadingMore}
        loadMoreNotice={loadMoreNotice}
        onLoadMore={onLoadMore}
      />

      <section className="dataset-results-list-section" aria-label="Ranked datasets">
        <div className="dataset-list-header">
          <strong>Ranked datasets</strong>
          <span>{candidateCount} retrieved</span>
        </div>
        <div className="dataset-results-list-pane" ref={listScrollRef}>
          <div className="dataset-list">
            {(candidates || []).map((candidate, index) => (
              <DatasetCard
                key={candidate.accession}
                candidate={candidate}
                rank={index + 1}
                isNew={newFromRank != null && index + 1 >= newFromRank}
                conceptMappings={mappings}
              />
            ))}
            {loadingMore ? <DatasetLoadMoreSkeleton count={2} /> : null}
          </div>

          {(!candidates || candidates.length === 0) && !loadingMore && (
            <p className="dataset-empty">No ranked dataset candidates returned.</p>
          )}
        </div>
      </section>
    </>
  )
}
