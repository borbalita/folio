import { ExternalLink } from 'lucide-react'

import type { CitationData } from '@/lib/chat-messages'

export function WebDetails({ citation }: { citation: CitationData }) {
  const url = citation.url?.trim()
  if (!url) {
    return null
  }
  return (
    <>
      <p className="text-sm break-all">{url}</p>
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        className="mt-1 inline-flex items-center gap-1 text-sm text-citation underline-offset-2 hover:underline"
      >
        Open page
        <ExternalLink className="size-3.5" />
      </a>
    </>
  )
}
