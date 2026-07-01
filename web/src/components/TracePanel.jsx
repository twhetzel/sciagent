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
        title: 'Normalize',
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
      open={name === 'tool_execution' || name === 'error' || name === 'iteration' || name === 'normalize'}
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
        <p>Live agent plan → act → observe → synthesize</p>
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
