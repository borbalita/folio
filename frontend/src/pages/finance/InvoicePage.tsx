import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { CloseInvoice } from '@/components/finance/CloseInvoice'
import { EmailMessage } from '@/components/finance/EmailMessage'
import { InvoiceFields } from '@/components/finance/InvoiceFields'
import { InvoicePayment } from '@/components/finance/InvoicePayment'
import { PdfViewer } from '@/components/finance/PdfViewer'
import { Button } from '@/components/ui/button'
import { api, type Invoice, type InvoiceAttachment, type InvoiceDetail } from '@/lib/api'
import { formatTimestamp } from '@/lib/format'
import { describeApiError } from '@/lib/http'
import { useRefresh } from '@/lib/useRefresh'

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

  const refresh = useCallback(() => {
    if (!emailId) {
      return
    }
    api
      .getInvoice(emailId)
      .then(setLoaded)
      .catch(() => undefined)
  }, [emailId])
  useRefresh(refresh)

  if (!emailId) {
    return null
  }

  if (error?.emailId === emailId) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
        <p className="text-sm text-destructive">{error.message}</p>
        <Button render={<Link to="/finance/invoices" />}>Back to invoices</Button>
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
  const linked = new Set(loaded.invoices.map((invoice) => invoice.attachmentId))
  const unlinked = stored.filter((item) => !linked.has(item.id))

  function replaceInvoice(updated: Invoice) {
    setLoaded((current) =>
      current
        ? {
            ...current,
            invoices: current.invoices.map((invoice) =>
              invoice.id === updated.id ? updated : invoice,
            ),
          }
        : current,
    )
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <article className="mx-auto flex max-w-7xl flex-col gap-6 p-6">
        <header className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 flex-col gap-1">
            <h1 className="text-lg font-semibold">{loaded.subject || '(no subject)'}</h1>
            <p className="text-sm text-muted-foreground">
              From {loaded.from}
              {sent ? ` · ${sent}` : ''}
            </p>
          </div>
          <CloseInvoice />
        </header>

        {loaded.invoices.map((invoice) => {
          const pdf = stored.find((item) => item.id === invoice.attachmentId)
          return (
            <section
              key={invoice.id}
              className="grid grid-cols-1 gap-6 border-t border-border pt-6 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]"
            >
              <div className="flex flex-col gap-6">
                <InvoiceFields invoice={invoice} onChange={replaceInvoice} />
                <InvoicePayment invoice={invoice} onChange={replaceInvoice} />
              </div>
              {pdf ? (
                <PdfViewer attachment={pdf} />
              ) : (
                <p className="text-sm text-muted-foreground">No PDF for this invoice.</p>
              )}
            </section>
          )
        })}

        {unlinked.length > 0 || skipped.length > 0 ? (
          <section className="flex flex-col gap-3 border-t border-border pt-6">
            <h2 className="text-sm font-medium text-muted-foreground">Other attachments</h2>
            {skipped.map((attachment) => (
              <SkippedAttachment key={attachment.id} attachment={attachment} />
            ))}
            {unlinked.map((attachment) => (
              <PdfViewer key={attachment.id} attachment={attachment} />
            ))}
          </section>
        ) : null}

        <section className="flex flex-col gap-2 border-t border-border pt-6">
          <h2 className="text-sm font-medium text-muted-foreground">Email message</h2>
          <EmailMessage body={loaded.body} />
        </section>
      </article>
    </div>
  )
}
