import { useCallback, useMemo, useState } from 'react'
import { postQuery } from './api.js'
import { toggleTheme } from './theme.js'
import ChatPanel from './components/ChatPanel.jsx'
import DatasetResultsPanel from './components/DatasetResultsPanel.jsx'
import TracePanel from './components/TracePanel.jsx'
import ToolsSidebar from './components/ToolsSidebar.jsx'
import './App.css'

export default function App() {
  const [messages, setMessages] = useState([])
  const [traces, setTraces] = useState([])
  const [datasetSearch, setDatasetSearch] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const activeTools = useMemo(() => {
    const names = new Set()
    for (const trace of traces) {
      for (const step of trace.steps || []) {
        if (step.name === 'tool_execution' && step.data?.tool) {
          names.add(step.data.tool)
        }
        if (step.name === 'plan' && step.data?.plan?.tools_needed) {
          step.data.plan.tools_needed.forEach((tool) => names.add(tool))
        }
      }
    }
    return [...names]
  }, [traces])

  const handleSubmit = useCallback(async (query) => {
    setLoading(true)
    setError(null)
    setDatasetSearch(null)
    setMessages((prev) => [...prev, { role: 'user', content: query }])

    try {
      const result = await postQuery(query)
      setMessages((prev) => [...prev, { role: 'assistant', content: result.response }])
      setTraces(result.traces || [])
      setDatasetSearch(result.dataset_search || null)
    } catch (err) {
      setError(err.message)
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Error: ${err.message}` },
      ])
    } finally {
      setLoading(false)
    }
  }, [])

  return (
    <div className="app-shell">
      <header className="top-bar">
        <span className="brand">SciAgent Studio</span>
        <button type="button" className="theme-toggle" onClick={toggleTheme}>
          Toggle theme
        </button>
      </header>

      {error && <div className="global-error">{error}</div>}

      <main className="layout">
        <ToolsSidebar activeTools={activeTools} />
        <div className="main-column">
          <ChatPanel messages={messages} loading={loading} onSubmit={handleSubmit} />
          <DatasetResultsPanel datasetSearch={datasetSearch} />
        </div>
        <TracePanel traces={traces} />
      </main>
    </div>
  )
}
