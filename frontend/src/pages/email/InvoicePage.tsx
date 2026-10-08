import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { api, type InvoiceAttachment, type InvoiceDetail } from '@/lib/api'
import { formatTimestamp } from '@/lib/format'
import { describeApiError } from '@/lib/http'

function PdfViewer({ attachment }: { attachment: InvoiceAttachment }) {
  const [state, setState] = useState<{ url: string } | { error: string } | null>(null)

  useEffect(() => {
    let cancelled = false
    let url: string | null = null
    api
      .getAttachment(attachment.id)
      .then((blob) => {
        if (cancelled) {
          return
        }
        url = URL.createObjectURL(blob)
        setState({ url })
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setState({ error: describeApiError(caught) })
        }
      })
    return () => {
      cancelled = true
      if (url) {
        URL.revokeObjectURL(url)
      }
    }
  }, [attachment.id])

  return (
    <figure className="flex flex-col gap-2">
      <figcaption className="text-sm font-medium">{attachment.filename}</figcaption>
      {state === null ? <p className="text-sm text-muted-foreground">Loading PDF…</p> : null}
      {state && 'error' in state ? <p className="text-sm text-destructive">{state.error}</p> : null}
      {state && 'url' in state ? (
        <iframe
          src={state.url}
          title={attachment.filename}
          className="h-[80vh] w-full rounded-md border border-border"
        />
      ) : null}
    </figure>
  )
}

function SkippedAttachment({ attachment }: { attachment: InvoiceAttachment }) {
  const reason =
    attachment.skippedReason === 'too_large'
      ? 'not stored (over 10 MB)'
      : `not stored (${attachment.skippedReason ?? 'unknown reason'})`
  return (
    <p className="text-sm">
      <span className="font-medium">{attachment.filename}</span>{' '}
      <span className="text-muted-foreground">— {reason}</span>
    </p>
  )
}

export function InvoicePage() {
  const { emailId } = useParams<{ emailId: string }>()
  const [loaded, setLoaded] = useState<InvoiceDetail | null>(null)
  const [error, setError] = useState<{ emailId: string; message: string } | null>(null)

  useEffect(() => {
    if (!emailId) {
      return
    }
    let cancelled = false
    api
      .getInvoice(emailId)
      .then((invoice) => {
        if (!cancelled) {
          setLoaded(invoice)
          setError(null)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setLoaded(null)
          setError({ emailId, message: describeApiError(caught) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [emailId])

  if (!emailId) {
    return null
  }

  if (error?.emailId === emailId) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
        <p className="text-sm text-destructive">{error.message}</p>
        <Button render={<Link to="/email" />}>Back to chats</Button>
      </div>
    )
  }

  if (loaded?.id !== emailId) {
    return (
      <div className="flex flex-1 items-center justify-center p-8 text-sm text-muted-foreground">
        Loading invoice…
      </div>
    )
  }

  const sent = formatTimestamp(loaded.sentAt)
  const stored = loaded.attachments.filter((item) => item.skippedReason === null)
  const skipped = loaded.attachments.filter((item) => item.skippedReason !== null)

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <article className="mx-auto flex max-w-4xl flex-col gap-6 p-6">
        <header className="flex flex-col gap-1">
          <h1 className="text-lg font-semibold">{loaded.subject || '(no subject)'}</h1>
          <p className="text-sm text-muted-foreground">
            From {loaded.from}
            {sent ? ` · ${sent}` : ''}
          </p>
        </header>

        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-medium text-muted-foreground">Attachments</h2>
          {loaded.attachments.length === 0 ? (
            <p className="text-sm text-muted-foreground">No PDF attachments.</p>
          ) : null}
          {skipped.map((attachment) => (
            <SkippedAttachment key={attachment.id} attachment={attachment} />
          ))}
          {stored.map((attachment) => (
            <PdfViewer key={attachment.id} attachment={attachment} />
          ))}
        </section>

        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-medium text-muted-foreground">Message</h2>
          <p className="whitespace-pre-wrap text-sm">{loaded.body}</p>
        </section>
      </article>
    </div>
  )
}
