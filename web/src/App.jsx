import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { postDatasetSearchMore, postQuery } from './api.js'
import { toggleTheme } from './theme.js'
import ChatInput from './components/ChatInput.jsx'
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
  const [loadingMore, setLoadingMore] = useState(false)
  const [loadMoreNotice, setLoadMoreNotice] = useState(null)
  const [newFromRank, setNewFromRank] = useState(null)
  const [error, setError] = useState(null)
  const scrollRef = useRef(null)
  const loadMoreNoticeTimerRef = useRef(null)

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

  useEffect(() => {
    return () => {
      if (loadMoreNoticeTimerRef.current) {
        window.clearTimeout(loadMoreNoticeTimerRef.current)
      }
    }
  }, [])

  useEffect(() => {
    if (!loadMoreNotice?.scrollToRank || !scrollRef.current) return
    const target = scrollRef.current.querySelector(
      `[data-candidate-rank="${loadMoreNotice.scrollToRank}"]`,
    )
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [loadMoreNotice])

  const handleSubmit = useCallback(async (query) => {
    setLoading(true)
    setError(null)
    setLoadMoreNotice(null)
    setNewFromRank(null)
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

  const handleLoadMore = useCallback(async () => {
    if (!datasetSearch?.load_more_cursor) return

    const priorCount = datasetSearch.candidates?.length ?? 0
    setLoadingMore(true)
    setError(null)
    setLoadMoreNotice(null)
    setNewFromRank(null)

    try {
      const result = await postDatasetSearchMore({
        load_more_cursor: datasetSearch.load_more_cursor,
        candidates: datasetSearch.candidates || [],
      })
      const updated = {
        ...result.dataset_search,
        search_strategies:
          result.dataset_search.search_strategies?.length > 0
            ? result.dataset_search.search_strategies
            : datasetSearch.search_strategies,
      }
      setDatasetSearch(updated)

      const total =
        updated.retrieved_count ?? updated.candidates?.length ?? priorCount
      const added = Math.max(0, result.added_count ?? total - priorCount)
      const scrollToRank = added > 0 ? priorCount + 1 : null

      if (added > 0) {
        setNewFromRank(priorCount + 1)
        window.setTimeout(() => setNewFromRank(null), 3200)
      }

      setLoadMoreNotice({ added, total, scrollToRank })
      if (loadMoreNoticeTimerRef.current) {
        window.clearTimeout(loadMoreNoticeTimerRef.current)
      }
      loadMoreNoticeTimerRef.current = window.setTimeout(() => {
        setLoadMoreNotice(null)
      }, 5000)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingMore(false)
    }
  }, [datasetSearch])

  return (
    <div className="app-shell">
      <header className="top-bar">
        <div className="top-bar-brand">
          <span className="brand">SciAgent Studio</span>
          <p className="top-bar-tagline">
            {datasetSearch
              ? 'Dataset discovery — refine your query and browse ranked results below'
              : 'Multi-database scientific search with transparent execution tracing'}
          </p>
        </div>
        <button type="button" className="theme-toggle" onClick={toggleTheme}>
          Toggle theme
        </button>
      </header>

      {error && <div className="global-error">{error}</div>}

      <main className="layout">
        <ToolsSidebar activeTools={activeTools} />
        <div className={`main-column${datasetSearch ? ' main-column--discovery' : ''}`}>
          <section className="query-panel" aria-label="Query">
            <p className="query-panel-label">
              {datasetSearch
                ? 'Refine your dataset query'
                : 'Enter your scientific query'}
            </p>
            <ChatInput onSubmit={handleSubmit} loading={loading} placement="top" />
          </section>
          {datasetSearch ? (
            <div className="dataset-workspace">
              <DatasetResultsPanel
                datasetSearch={datasetSearch}
                loadingMore={loadingMore}
                newFromRank={newFromRank}
                listScrollRef={scrollRef}
                messages={messages}
                loading={loading}
                loadMoreNotice={loadMoreNotice}
                onLoadMore={handleLoadMore}
              />
            </div>
          ) : (
            <div className="main-column-scroll">
              <ChatPanel messages={messages} loading={loading} />
            </div>
          )}
        </div>
        <TracePanel traces={traces} />
      </main>
    </div>
  )
}
