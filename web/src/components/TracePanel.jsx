function formatDuration(seconds) {
  if (seconds == null) return '—'
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`
  return `${seconds.toFixed(2)}s`
}

function statusClass(status) {
  if (status === 'completed') return 'trace-status--ok'
  if (status === 'error') return 'trace-status--error'
  return 'trace-status--running'
}

const DATASET_DISCOVERY_STEPS = new Set([
  'interpret_query',
  'ground_query',
  'search_repository',
  'normalize_records',
  'annotate_evidence',
  'rank_results',
  'respond',
])

function stepClass(name, data) {
  if (name === 'error') return 'trace-step--error'
  if (name === 'tool_execution') {
    return data?.status === 'error' ? 'trace-step--error' : 'trace-step--tool'
  }
  if (name === 'plan') return 'trace-step--plan'
  if (name === 'iteration') return 'trace-step--iteration'
  if (name === 'observe') return 'trace-step--observe'
  if (name === 'synthesize') return 'trace-step--synth'
  if (name === 'normalize') return 'trace-step--normalize'
  if (name === 'normalize_records') return 'trace-step--tool'
  if (name === 'search_repository') return 'trace-step--tool'
  if (name === 'annotate_evidence') return 'trace-step--observe'
  if (name === 'rank_results') return 'trace-step--synth'
  if (name === 'respond') return 'trace-step--plan'
  if (DATASET_DISCOVERY_STEPS.has(name)) return 'trace-step--plan'
  return 'trace-step--default'
}

function getIterationContext(steps, stepIndex) {
  const iterationNum = steps[stepIndex]?.data?.iteration ?? stepIndex + 1

  let plannedTools = []
  for (let i = stepIndex - 1; i >= 0; i -= 1) {
    const step = steps[i]
    if (step.name === 'plan') {
      plannedTools = step.data?.plan?.tools_needed || []
      break
    }
    if (step.name === 'synthesize') {
      plannedTools = step.data?.updated_plan?.tools_needed || []
      break
    }
  }

  const executedTools = []
  const toolStatuses = []
  for (let i = stepIndex + 1; i < steps.length; i += 1) {
    const step = steps[i]
    if (step.name === 'observe' || step.name === 'iteration') break
    if (step.name === 'tool_execution' && step.data?.tool) {
      executedTools.push(step.data.tool)
      toolStatuses.push({
        tool: step.data.tool,
        status: step.data.status || 'unknown',
      })
    }
  }

  return { iterationNum, plannedTools, executedTools, toolStatuses }
}

function summarizeIteration(data, steps, stepIndex) {
  const { iterationNum, plannedTools, executedTools, toolStatuses } = getIterationContext(
    steps,
    stepIndex,
  )

  if (executedTools.length > 0) {
    const successCount = toolStatuses.filter((t) => t.status === 'success').length
    const failed = toolStatuses.filter((t) => t.status === 'error').map((t) => t.tool)
    let summary = `Running ${executedTools.join(', ')}`
    if (failed.length > 0) {
      summary += ` (${successCount}/${executedTools.length} succeeded)`
    }
    return {
      title: `Iteration ${iterationNum}`,
      summary,
      chips: executedTools,
    }
  }

  if (plannedTools.length > 0 && iterationNum === 1) {
    return {
      title: `Iteration ${iterationNum}`,
      summary: `Scheduled: ${plannedTools.join(', ')}`,
      chips: plannedTools,
    }
  }

  if (iterationNum > 1) {
    return {
      title: `Iteration ${iterationNum}`,
      summary: 'Re-evaluating plan (no new tool calls)',
      chips: plannedTools,
    }
  }

  return {
    title: `Iteration ${iterationNum}`,
    summary: 'No tools scheduled for this iteration',
    chips: [],
  }
}

function summarizeStep(name, data, steps, stepIndex) {
  switch (name) {
    case 'plan':
      return {
        title: 'Plan',
        summary: data?.plan?.goal || 'Planning query execution',
        chips: data?.plan?.tools_needed || [],
      }
    case 'iteration':
      return summarizeIteration(data, steps, stepIndex)
    case 'tool_execution':
      return {
        title: `Tool: ${data?.tool || 'unknown'}`,
        summary:
          data?.status === 'success'
            ? summarizeToolResult(data)
            : data?.error || 'Tool execution failed',
        chips: data?.status ? [data.status] : [],
      }
    case 'observe':
      return {
        title: 'Observe',
        summary: `${data?.successful_actions ?? 0} succeeded, ${data?.failed_actions ?? 0} failed`,
        chips: [],
      }
    case 'synthesize':
      return {
        title: 'Synthesize',
        summary: data?.updated_plan?.needs_retry ? 'Plan updated — retry needed' : 'Plan updated',
        chips: data?.updated_plan?.tools_needed || [],
      }
    case 'normalize':
      return {
        title: 'Normalize (tool results)',
        summary:
          data?.status === 'skipped'
            ? 'No terms to normalize'
            : data?.status === 'error'
              ? data?.error || 'Normalization failed'
              : `${data?.matched ?? 0} matched, ${data?.unmatched ?? 0} unmatched`,
        chips: (data?.mappings || [])
          .filter((m) => m.match_type && m.match_type !== 'unmatched')
          .slice(0, 4)
          .map((m) => m.curie || m.label)
          .filter(Boolean),
      }
    case 'interpret_query':
      return {
        title: data?.label || 'Interpret Query',
        summary: [
          data?.interpreted_query?.disease && `disease: ${data.interpreted_query.disease}`,
          data?.interpreted_query?.tissue && `tissue: ${data.interpreted_query.tissue}`,
          data?.interpreted_query?.assay && `assay: ${data.interpreted_query.assay}`,
          data?.interpreted_query?.organism && `organism: ${data.interpreted_query.organism}`,
        ]
          .filter(Boolean)
          .join(', ') || 'Extract query facets',
        chips: [],
      }
    case 'ground_query':
      return {
        title: data?.label || 'Ground Query',
        summary: `${data?.mapping_count ?? 0} requested facet(s) mapped to ontology concepts`,
        chips: (data?.concept_mappings || [])
          .slice(0, 4)
          .map((m) => m.curie || m.label)
          .filter(Boolean),
      }
    case 'search_repository':
      return {
        title: data?.label || 'Search Repository',
        summary: `${data?.record_count ?? 0} GEO record(s) retrieved (${data?.total_found ?? 0} total hits)`,
        chips: data?.repository ? [data.repository] : [],
      }
    case 'normalize_records':
      return {
        title: data?.label || 'Normalize Records',
        summary: `${data?.candidate_count ?? 0} DatasetCandidate record(s) from ${data?.input_records ?? 0} GEO payload(s)`,
        chips: data?.repository ? [data.repository] : [],
      }
    case 'annotate_evidence':
      return {
        title: data?.label || 'Annotate Evidence',
        summary: `${data?.evidence_snippet_count ?? 0} evidence snippet(s) across ${data?.candidate_count ?? 0} candidate(s)`,
        chips: data?.warning_count != null ? [`${data.warning_count} warnings`] : [],
      }
    case 'rank_results':
      return {
        title: data?.label || 'Rank Results',
        summary: `${data?.candidate_count ?? 0} candidate(s); ${data?.full_matches ?? 0} full, ${data?.partial_matches ?? 0} partial`,
        chips: data?.top_accessions || [],
      }
    case 'respond':
      return {
        title: data?.label || 'Respond',
        summary: `Rendered ${data?.candidate_count ?? 0} ranked dataset result(s)`,
        chips: [],
      }
    case 'error':
      return {
        title: 'Error',
        summary: data?.error || data?.message || 'An error occurred',
        chips: [],
      }
    default:
      return { title: name, summary: 'Step recorded', chips: [] }
  }
}

function summarizeToolResult(data) {
  const payload = data?.data
  if (!payload || typeof payload !== 'object') return 'Completed'

  if (data?.tool === 'geo_dataset_search') {
    const count = payload.candidate_count ?? payload.total_found
    return count != null ? `Found ${count} GEO dataset(s)` : 'GEO search completed'
  }
  if (payload.results && Array.isArray(payload.results)) {
    return `Found ${payload.results.length} result(s)`
  }
  if (payload.variants && Array.isArray(payload.variants)) {
    return `Found ${payload.variants.length} variant(s)`
  }
  if (payload.found === true) {
    return payload.symbol || payload.accession || payload.uniprot_id || 'Record found'
  }
  if (payload.error) return payload.error
  return 'Completed'
}

function StepCard({ step, steps, stepIndex }) {
  const { name, timestamp, data } = step
  const info = summarizeStep(name, data, steps, stepIndex)

  return (
    <details
      className={`trace-step ${stepClass(name, data)}`}
      open={
        name === 'tool_execution' ||
        name === 'error' ||
        name === 'iteration' ||
        name === 'normalize' ||
        DATASET_DISCOVERY_STEPS.has(name)
      }
    >
      <summary>
        <span className="trace-step-name">{info.title}</span>
        <span className="trace-step-summary">{info.summary}</span>
        {timestamp && (
          <time className="trace-step-time">{new Date(timestamp).toLocaleTimeString()}</time>
        )}
      </summary>
      <div className="trace-step-body">
        {info.chips.length > 0 && (
          <div className="trace-chips">
            {info.chips.map((chip) => (
              <span key={chip} className="trace-chip">
                {chip}
              </span>
            ))}
          </div>
        )}
        <pre>{JSON.stringify(data, null, 2)}</pre>
      </div>
    </details>
  )
}

function TraceDocument({ trace }) {
  const query = trace.metadata?.query || 'Unknown query'

  return (
    <article className="trace-document">
      <header className="trace-doc-header">
        <div>
          <span className={`trace-status ${statusClass(trace.status)}`}>{trace.status}</span>
          <span className="trace-duration">{formatDuration(trace.duration_seconds)}</span>
        </div>
        <p className="trace-query">{query}</p>
      </header>

      <div className="trace-timeline">
        {(trace.steps || []).map((step, index) => (
          <StepCard key={`${step.name}-${index}`} step={step} steps={trace.steps} stepIndex={index} />
        ))}
      </div>
    </article>
  )
}

export default function TracePanel({ traces }) {
  return (
    <aside className="trace-panel">
      <header className="trace-header">
        <h2>Execution Trace</h2>
        <p>Standard path: plan → act → observe → normalize. Dataset discovery uses its own labeled steps.</p>
      </header>

      <div className="trace-content">
        {(!traces || traces.length === 0) && (
          <div className="trace-empty">
            <p>Run a query to see the execution trace here.</p>
            <p className="trace-empty-hint">
              Each step shows planning decisions, tool calls, and observations — not just the final answer.
            </p>
          </div>
        )}

        {traces?.map((trace) => (
          <TraceDocument key={trace.id + (trace.start_time || '')} trace={trace} />
        ))}
      </div>
    </aside>
  )
}
