import { X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { type CitationData } from '@/lib/chat-messages'

interface SourcePanelProps {
  citation: CitationData | null
  onClose: () => void
}

function formatFilingDate(iso: string | undefined): string | null {
  if (!iso) {
    return null
  }
  const parts = iso.split('-').map(Number)
  const year = parts[0]
  const month = parts[1]
  const day = parts[2]
  if (!year || !month || !day) {
    return null
  }
  const date = new Date(year, month - 1, day)
  if (Number.isNaN(date.getTime())) {
    return null
  }
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date)
}

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

export function SourcePanel({ citation, onClose }: SourcePanelProps) {
  if (citation === null) {
    return (
      <div className="flex h-full items-center p-4">
        <p className="text-sm text-muted-foreground">
          Select a citation to read the filing passage.
        </p>
      </div>
    )
  }

  const company = citation.companyName?.trim()
  const ticker = citation.ticker?.trim()
  const filing = filingLine(citation)
  const filed = formatFilingDate(citation.filingDate)
  const location = locationLine(citation)
  const excerpt = citation.excerpt?.trim()

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-start justify-between gap-2 border-b px-4 py-3">
        <div className="min-w-0">
          {company ? <p className="font-medium leading-snug">{company}</p> : null}
          {ticker ? <p className="mt-0.5 text-sm text-citation">{ticker}</p> : null}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label="Close filing passage"
          onClick={onClose}
        >
          <X />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        {filing ? <p className="text-sm">{filing}</p> : null}
        {filed ? <p className="mt-1 text-sm text-muted-foreground">Filed {filed}</p> : null}
        {location ? <p className="mt-1 text-sm text-muted-foreground">{location}</p> : null}
        {excerpt ? (
          <p className="mt-4 text-sm leading-relaxed">{excerpt}</p>
        ) : null}
      </div>
    </div>
  )
}
