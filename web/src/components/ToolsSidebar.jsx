import { useEffect, useState } from 'react'
import { getTools } from '../api.js'

const TOOL_ICONS = {
  pubmed: '📄',
  openalex: '📚',
  europepmc: '📰',
  expression_atlas: '🧫',
  mygene: '🧬',
  uniprot: '🧪',
  clinvar: '⚕️',
  alphafold: '🔬',
  summarize: '✨',
  geo_dataset_search: '🗂️',
  immport: '🛡️',
}

export default function ToolsSidebar({ activeTools = [] }) {
  const [tools, setTools] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    getTools()
      .then((data) => {
        if (!cancelled) {
          setTools(data)
          setError(null)
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <aside className="tools-sidebar">
      <div className="sidebar-header">
        <h2>Resources</h2>
        <p>Available scientific databases</p>
      </div>

      {loading && <p className="sidebar-status">Loading tools…</p>}
      {error && <p className="sidebar-error">{error}</p>}

      <ul className="tool-list">
        {tools.map((tool) => {
          const isActive = activeTools.includes(tool.name)
          const params = tool.parameters ? Object.keys(tool.parameters) : []
          return (
            <li key={tool.name} className={`tool-card ${isActive ? 'tool-card--active' : ''}`}>
              <div className="tool-card-header">
                <span className="tool-icon">{TOOL_ICONS[tool.name] || '🔧'}</span>
                <span className="tool-name">{tool.name}</span>
                {isActive && <span className="tool-used-badge">used</span>}
              </div>
              <p className="tool-description">{tool.description}</p>
              {params.length > 0 && (
                <div className="tool-params">
                  {params.map((param) => (
                    <span key={param} className="param-chip">
                      {param}
                    </span>
                  ))}
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
