import { X } from 'lucide-react'

import { FilingDetails } from '@/components/chat/FilingDetails'
import { MailDetails } from '@/components/chat/MailDetails'
import { NewsDetails } from '@/components/chat/NewsDetails'
import { Button } from '@/components/ui/button'
import {
  citationKind,
  newsSourceName,
  type CitationData,
  type CitationKind,
} from '@/lib/chat-messages'

interface SourcePanelProps {
  citation: CitationData | null
  onClose: () => void
}

function heading(citation: CitationData, kind: CitationKind) {
  if (kind === 'news') {
    return { title: citation.title?.trim(), subtitle: newsSourceName(citation.source) }
  }
  if (kind === 'mail') {
    return { title: citation.subject?.trim(), subtitle: citation.from?.trim() }
  }
  return { title: citation.companyName?.trim(), subtitle: citation.ticker?.trim() }
}

export function SourcePanel({ citation, onClose }: SourcePanelProps) {
  if (citation === null) {
    return (
      <div className="flex h-full items-center p-4">
        <p className="text-sm text-muted-foreground">Select a citation to read the source.</p>
      </div>
    )
  }

  const kind = citationKind(citation)
  const { title, subtitle } = heading(citation, kind)
  const excerpt = citation.excerpt?.trim()

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-start justify-between gap-2 border-b px-4 py-3">
        <div className="min-w-0">
          {title ? <p className="font-medium leading-snug">{title}</p> : null}
          {subtitle ? <p className="mt-0.5 truncate text-sm text-citation">{subtitle}</p> : null}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label="Close source"
          onClick={onClose}
        >
          <X />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        {kind === 'news' ? <NewsDetails citation={citation} /> : null}
        {kind === 'mail' ? <MailDetails citation={citation} /> : null}
        {kind === 'filing' ? <FilingDetails citation={citation} /> : null}
        {excerpt ? <p className="mt-4 text-sm leading-relaxed">{excerpt}</p> : null}
      </div>
    </div>
  )
}
