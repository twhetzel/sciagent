import Tooltip from './Tooltip.jsx'
import {
  facetStatusDescription,
  facetStatusShortLabel,
  facetStatusLabel,
} from '../utils/facetCoverage.js'

function FacetStatusTooltipContent({ status }) {
  return (
    <span className="facet-status-tooltip-content">
      <strong className="facet-status-tooltip-title">{facetStatusLabel(status)}</strong>
      <span className="facet-status-tooltip-description">
        {facetStatusDescription(status)}
      </span>
    </span>
  )
}

export function FacetStatusLabelTooltip({ status, className = '' }) {
  return (
    <Tooltip
      className={className}
      content={<FacetStatusTooltipContent status={status} />}
    >
      <span className="facet-status-tooltip-label">{facetStatusShortLabel(status)}</span>
    </Tooltip>
  )
}

export function FacetStatusInfoTooltip({
  status,
  detail,
  className = '',
  children,
}) {
  const content = detail ? (
    <span className="facet-status-tooltip-content">
      <strong className="facet-status-tooltip-title">{detail}</strong>
      <span className="facet-status-tooltip-description">
        {facetStatusDescription(status)}
      </span>
    </span>
  ) : (
    <FacetStatusTooltipContent status={status} />
  )

  return (
    <Tooltip className={className} content={content}>
      {children || (
        detail ? (
          <span className="facet-status-tooltip-label">{detail}</span>
        ) : (
          <span className={`facet-coverage-swatch facet-coverage-swatch--${status}`} />
        )
      )}
    </Tooltip>
  )
}
