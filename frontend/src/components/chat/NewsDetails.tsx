import { ExternalLink } from 'lucide-react'

import type { CitationData } from '@/lib/chat-messages'
import { formatIsoDay } from '@/lib/format'

export function NewsDetails({ citation }: { citation: CitationData }) {
  const edition = formatIsoDay(citation.date)
  const url = citation.url?.trim()
  return (
    <>
      {edition ? <p className="text-sm">Edition of {edition}</p> : null}
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="mt-1 inline-flex items-center gap-1 text-sm text-citation underline-offset-2 hover:underline"
        >
          Open article
          <ExternalLink className="size-3.5" />
        </a>
      ) : null}
    </>
  )
}
