import { useState } from 'react'

function renderResponse(text) {
  if (!text) return null
  return text.split('\n').map((line, i) => {
    if (line.startsWith('**') && line.endsWith('**')) {
      return (
        <strong key={i} className="response-heading">
          {line.replace(/\*\*/g, '')}
        </strong>
      )
    }
    if (/^\d+\.\s\*\*/.test(line)) {
      return (
        <h3 key={i} className="response-section">
          {line.replace(/\*\*/g, '')}
        </h3>
      )
    }
    if (line.trim() === '') {
      return <br key={i} />
    }
    return (
      <p key={i} className="response-line">
        {line}
      </p>
    )
  })
}

export default function ChatPanel({ onSubmit, loading, messages }) {
  const [query, setQuery] = useState('')

  function handleSubmit(event) {
    event.preventDefault()
    const trimmed = query.trim()
    if (!trimmed || loading) return
    onSubmit(trimmed)
    setQuery('')
  }

  return (
    <section className="chat-panel">
      <header className="chat-header">
        <div>
          <h1>SciAgent</h1>
          <p>Multi-database scientific search with transparent execution tracing</p>
        </div>
      </header>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>Ask about genes, proteins, variants, structures, or literature.</p>
            <ul>
              <li>BRCA1 gene information</li>
              <li>TP53 variants in ClinVar</li>
              <li>breast cancer literature</li>
              <li>AlphaFold structure for EGFR</li>
            </ul>
          </div>
        )}

        {messages.map((msg, index) => (
          <div key={index} className={`message message--${msg.role}`}>
            <div className="message-label">{msg.role === 'user' ? 'You' : 'SciAgent'}</div>
            <div className="message-body">
              {msg.role === 'assistant' ? renderResponse(msg.content) : msg.content}
            </div>
          </div>
        ))}

        {loading && (
          <div className="message message--assistant">
            <div className="message-label">SciAgent</div>
            <div className="message-body loading-pulse">Searching databases…</div>
          </div>
        )}
      </div>

      <form className="chat-form" onSubmit={handleSubmit}>
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Enter your scientific query…"
          rows={3}
          disabled={loading}
        />
        <button type="submit" disabled={loading || !query.trim()}>
          {loading ? 'Running…' : 'Run query'}
        </button>
      </form>
    </section>
  )
}
