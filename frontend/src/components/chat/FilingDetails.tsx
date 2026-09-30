import type { CitationData } from '@/lib/chat-messages'
import { formatIsoDay } from '@/lib/format'

function filingLine(citation: CitationData): string | null {
  const bits: string[] = []
  if (citation.form?.trim()) {
    bits.push(citation.form.trim())
  }
  if (citation.fiscalYear != null) {
    bits.push(`FY${citation.fiscalYear}`)
  }
  return bits.length > 0 ? bits.join(' ') : null
}

function locationLine(citation: CitationData): string | null {
  const bits: string[] = []
  if (citation.page?.trim()) {
    bits.push(`p. ${citation.page.trim()}`)
  }
  if (citation.section?.trim()) {
    bits.push(citation.section.trim())
  }
  return bits.length > 0 ? bits.join('  ') : null
}

export function FilingDetails({ citation }: { citation: CitationData }) {
  const filing = filingLine(citation)
  const filed = formatIsoDay(citation.filingDate)
  const location = locationLine(citation)
  return (
    <>
      {filing ? <p className="text-sm">{filing}</p> : null}
      {filed ? <p className="mt-1 text-sm text-muted-foreground">Filed {filed}</p> : null}
      {location ? <p className="mt-1 text-sm text-muted-foreground">{location}</p> : null}
    </>
  )
}
