import { useState } from 'react'

export default function ChatInput({ onSubmit, loading, placement = 'bottom' }) {
  const [query, setQuery] = useState('')

  function submitQuery() {
    const trimmed = query.trim()
    if (!trimmed || loading) return
    onSubmit(trimmed)
    setQuery('')
  }

  function handleSubmit(event) {
    event.preventDefault()
    submitQuery()
  }

  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submitQuery()
    }
  }

  return (
    <form
      className={`chat-form${placement === 'top' ? ' chat-form--top' : ''}`}
      onSubmit={handleSubmit}
    >
      <textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Enter your scientific query…"
        rows={3}
        disabled={loading}
      />
      <button type="submit" disabled={loading || !query.trim()}>
        {loading ? 'Running…' : 'Run query'}
      </button>
    </form>
  )
}
