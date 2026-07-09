export default function DatasetSearchOptionsPanel({
  includeTextBroad,
  onIncludeTextBroadChange,
  disabled = false,
}) {
  return (
    <div className="dataset-search-options">
      <label className="dataset-search-options-label">
        <input
          type="checkbox"
          checked={includeTextBroad}
          onChange={(event) => onIncludeTextBroadChange(event.target.checked)}
          disabled={disabled}
        />
        <span>
          Include <code>text_broad</code> free-text supplement
        </span>
      </label>
    </div>
  )
}
