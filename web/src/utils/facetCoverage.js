export const FACET_ORDER = ['disease', 'tissue', 'assay', 'organism']

export const FACET_STATUS_ORDER = ['supported', 'warning', 'conflict', 'absent']

export const FACET_STATUS_META = {
  supported: {
    label: 'Supported',
    title: 'Supported by metadata',
    description:
      'Returned GEO metadata explicitly supports this grounded concept — matching terms appear in fields such as title, summary, or structured assay/organism annotations.',
  },
  warning: {
    label: 'Warning',
    title: 'Supported with warnings',
    description:
      'Evidence points toward this concept, but metadata is ambiguous or incomplete — for example organoid-derived tissue, organism named only in narrative text, or other cautionary signals that fall short of a direct contradiction.',
  },
  conflict: {
    label: 'Conflict',
    title: 'Evidence conflict',
    description:
      'Metadata fields disagree about this facet — for example the title describes one assay while structured fields indicate another, without clear support for the requested concept.',
  },
  absent: {
    label: 'Absent',
    title: 'Not supported in metadata',
    description:
      'This grounded concept was requested in the query, but no returned metadata field provides supporting evidence for it.',
  },
}

const SLOT_KEYWORDS = {
  disease: ['disease', 'mondo'],
  tissue: ['tissue', 'derived', 'model tissue', 'ambiguous tissue', 'colon', 'organ'],
  assay: ['assay', 'rna-seq', 'sequencing', 'multi-assay', 'mixed'],
  organism: ['organism', 'species', 'taxon', 'mus musculus', 'animal model', 'human'],
}

export function facetLabel(slot, mappings) {
  const mapping = mappings?.find((item) => item.slot === slot)
  return mapping?.label || slot
}

function messageMentionsSlot(message, slot) {
  const lower = String(message || '').toLowerCase()
  return (SLOT_KEYWORDS[slot] || [slot]).some((keyword) => lower.includes(keyword))
}

/** Informational multi-assay notices — not a disagreement when requested assay is present. */
function isMultiAssayNotice(message) {
  const lower = String(message || '').toLowerCase()
  return (
    lower.includes('multiple assay types detected across metadata fields')
    || lower.includes('metadata appears to include multiple assay types')
    || lower.includes('labeled as mixed or multi-assay')
  )
}

function assayQualifyingWarnings(warnings, slotData) {
  if (!slotData?.present) return warnings || []
  return (warnings || []).filter((message) => !isMultiAssayNotice(message))
}

/**
 * Derive a single facet cell state from score_breakdown audit data.
 * Returns null when the facet was not requested in the query.
 */
export function deriveFacetStatus(slot, breakdown, requestedSlots) {
  if (!requestedSlots?.has(slot)) return null

  const slotData = breakdown?.[slot]
  if (!slotData?.present) return 'absent'

  const conflicts = breakdown?.evidence_conflicts || []
  if (conflicts.some((message) => messageMentionsSlot(message, slot))) {
    return 'conflict'
  }

  if (slot === 'tissue' && ['derived_model', 'ambiguous'].includes(slotData.evidence_type)) {
    return 'warning'
  }

  if (slot === 'organism' && slotData.evidence_source === 'narrative') {
    return 'warning'
  }

  const warnings =
    slot === 'assay'
      ? assayQualifyingWarnings(breakdown?.warnings, slotData)
      : breakdown?.warnings || []
  if (warnings.some((message) => messageMentionsSlot(message, slot))) {
    return 'warning'
  }

  return 'supported'
}

export function facetStatusLabel(status) {
  return FACET_STATUS_META[status]?.title || 'Unknown'
}

export function facetStatusShortLabel(status) {
  return FACET_STATUS_META[status]?.label || status
}

export function facetStatusDescription(status) {
  return FACET_STATUS_META[status]?.description || ''
}

export function requestedFacetSlots(mappings) {
  const slots = new Set()
  for (const mapping of mappings || []) {
    if (FACET_ORDER.includes(mapping.slot)) {
      slots.add(mapping.slot)
    }
  }
  return FACET_ORDER.filter((slot) => slots.has(slot))
}

export function emptyFacetCounts() {
  return { supported: 0, warning: 0, conflict: 0, absent: 0 }
}

/** Aggregate facet evidence counts across all ranked candidates. */
export function buildFacetSummary(candidates, mappings) {
  const requestedSlots = requestedFacetSlots(mappings)
  const total = candidates?.length ?? 0
  if (!requestedSlots.length || !total) {
    return { rows: [], total: 0 }
  }

  const requestedSet = new Set(requestedSlots)
  const rows = requestedSlots.map((slot) => {
    const counts = emptyFacetCounts()
    const mapping = mappings?.find((item) => item.slot === slot)

    for (const candidate of candidates) {
      const status = deriveFacetStatus(slot, candidate.score_breakdown, requestedSet)
      if (status) counts[status] += 1
    }

    return {
      slot,
      label: facetLabel(slot, mappings),
      curie: mapping?.curie,
      counts,
    }
  })

  return { rows, total }
}
