import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getConfig, postDatasetSearchMore, postQuery } from './api.js'
import { toggleTheme } from './theme.js'
import ChatInput from './components/ChatInput.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import DatasetResultsPanel from './components/DatasetResultsPanel.jsx'
import DatasetSearchOptionsPanel from './components/DatasetSearchOptionsPanel.jsx'
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
  const [manifestSelectedAccessions, setManifestSelectedAccessions] = useState(() => new Set())
  const [error, setError] = useState(null)
  const [includeTextBroad, setIncludeTextBroad] = useState(true)
  const scrollRef = useRef(null)
  const loadMoreNoticeTimerRef = useRef(null)

  useEffect(() => {
    getConfig()
      .then((config) => {
        const defaultValue = config?.dataset_search_defaults?.include_text_broad
        if (typeof defaultValue === 'boolean') {
          setIncludeTextBroad(defaultValue)
        }
      })
      .catch(() => {
        // Keep local default when config is unavailable.
      })
  }, [])

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
    setManifestSelectedAccessions(new Set())
    setMessages((prev) => [...prev, { role: 'user', content: query }])

    try {
      const result = await postQuery(query, { include_text_broad: includeTextBroad })
      setMessages((prev) => [...prev, { role: 'assistant', content: result.response }])
      setTraces(result.traces || [])
      setDatasetSearch(result.dataset_search || null)
      if (typeof result.dataset_search?.include_text_broad === 'boolean') {
        setIncludeTextBroad(result.dataset_search.include_text_broad)
      }
    } catch (err) {
      setError(err.message)
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Error: ${err.message}` },
      ])
    } finally {
      setLoading(false)
    }
  }, [includeTextBroad])

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

  const handleToggleManifestSelection = useCallback((accession) => {
    setManifestSelectedAccessions((prev) => {
      const next = new Set(prev)
      if (next.has(accession)) {
        next.delete(accession)
      } else {
        next.add(accession)
      }
      return next
    })
  }, [])

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
            <p className="query-panel-label">Enter your scientific query</p>
            <DatasetSearchOptionsPanel
              includeTextBroad={includeTextBroad}
              onIncludeTextBroadChange={setIncludeTextBroad}
              disabled={loading}
            />
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
                manifestSelectedAccessions={manifestSelectedAccessions}
                onToggleManifestSelection={handleToggleManifestSelection}
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
