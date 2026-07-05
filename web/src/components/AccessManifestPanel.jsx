import {
  buildManifestExport,
  buildManifestMarkdown,
  downloadTextFile,
} from '../utils/datasetAccess.js'

export default function AccessManifestPanel({
  candidates,
  selectedAccessions,
  datasetSearch,
}) {
  const count = selectedAccessions?.size ?? 0
  const exportOptions = { datasetSearch }

  function handleExportJson() {
    const manifest = buildManifestExport(candidates, selectedAccessions, exportOptions)
    downloadTextFile(
      JSON.stringify(manifest, null, 2),
      'access-manifest.json',
      'application/json',
    )
  }

  function handleExportMarkdown() {
    const markdown = buildManifestMarkdown(candidates, selectedAccessions, exportOptions)
    downloadTextFile(markdown, 'access-manifest.md', 'text/markdown')
  }

  return (
    <section className="access-manifest-panel" aria-label="Access manifest">
      <div className="access-manifest-panel-main">
        <div className="access-manifest-panel-heading">
          <strong>Access manifest</strong>
          <span className="access-manifest-panel-count">
            {count} selected {count === 1 ? 'dataset' : 'datasets'}
          </span>
        </div>
        <p className="access-manifest-panel-note">
          Add datasets from the ranked list to build an access manifest for export. Direct
          downloading is not available yet — this exports access metadata only.
        </p>
      </div>
      <div className="access-manifest-panel-actions">
        <button
          type="button"
          className="access-manifest-export-button"
          onClick={handleExportJson}
          disabled={count === 0}
        >
          Export manifest JSON
        </button>
        <button
          type="button"
          className="access-manifest-export-button access-manifest-export-button--secondary"
          onClick={handleExportMarkdown}
          disabled={count === 0}
        >
          Export manifest Markdown
        </button>
      </div>
    </section>
  )
}
