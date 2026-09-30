import type { CitationData } from '@/lib/chat-messages'
import { formatIsoDay } from '@/lib/format'

export function MailDetails({ citation }: { citation: CitationData }) {
  const sent = formatIsoDay(citation.date)
  const mailbox = citation.mailbox?.trim()
  return (
    <>
      {sent ? <p className="text-sm">Sent {sent}</p> : null}
      {mailbox ? <p className="mt-1 text-sm text-muted-foreground">{mailbox}</p> : null}
    </>
  )
}
