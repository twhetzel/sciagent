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

export default function ChatPanel({ loading, messages, compact = false }) {
  const visibleMessages =
    compact && messages.length > 2 ? messages.slice(-2) : messages

  return (
    <section className={`chat-panel${compact ? ' chat-panel--compact' : ''}`}>
      {compact && messages.length > 0 ? (
        <div className="chat-panel-compact-label">Latest query</div>
      ) : null}
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>Try an example below. The trace panel shows different steps depending on query type.</p>
            <p className="chat-empty-section">Dataset discovery (Interpret Query → Ground Query → Search → Normalize Records → Annotate → Rank → Respond)</p>
            <ul>
              <li>Find public RNA-seq datasets for ulcerative colitis colon tissue</li>
            </ul>
            <p className="chat-empty-section">Gene / variant search (includes Normalize tool results)</p>
            <ul>
              <li>BRCA1 gene information</li>
              <li>TP53 variants in ClinVar</li>
              <li>marfan syndrome variants</li>
              <li>AlphaFold structure for EGFR</li>
            </ul>
          </div>
        )}

        {visibleMessages.map((msg, index) => (
          <div key={`${index}-${msg.role}-${msg.content.slice(0, 24)}`}>
            {msg.role === 'user' && index > 0 && !compact && (
              <hr className="chat-turn-divider" aria-hidden="true" />
            )}
            <div className={`message message--${msg.role}`}>
              <div className="message-label">{msg.role === 'user' ? 'You' : 'SciAgent Studio'}</div>
              <div className="message-body">
                {msg.role === 'assistant' ? renderResponse(msg.content) : msg.content}
              </div>
            </div>
          </div>
        ))}

        {loading && (
          <div className="message message--assistant">
            <div className="message-label">SciAgent Studio</div>
            <div className="message-body loading-pulse">Searching databases…</div>
          </div>
        )}
      </div>
    </section>
  )
}
