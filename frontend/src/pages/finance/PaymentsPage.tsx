import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { PaymentCard } from '@/components/finance/PaymentCard'
import { PdfViewer } from '@/components/finance/PdfViewer'
import { Button } from '@/components/ui/button'
import { api, type PaymentDraft } from '@/lib/api'
import { describeApiError } from '@/lib/http'
import { useRefresh } from '@/lib/useRefresh'

type State = { drafts: PaymentDraft[] } | { error: string } | null

/** Prepared payments, one card at a time, each beside its invoice. */
export function PaymentsPage() {
  const [params] = useSearchParams()
  const ids = (params.get('drafts') ?? '').split(',').filter(Boolean)
  const key = ids.join(',')
  const [state, setState] = useState<State>(null)
  const [index, setIndex] = useState(0)

  useEffect(() => {
    if (!key) {
      return
    }
    let cancelled = false
    api
      .getPaymentDrafts(key.split(','))
      .then((drafts) => {
        if (!cancelled) {
          setState({ drafts })
          setIndex(0)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setState({ error: describeApiError(caught) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [key])

  const refresh = useCallback(() => {
    if (!key) {
      return
    }
    // Keeps the current card: a booking elsewhere completes a payment without a reload.
    api
      .getPaymentDrafts(key.split(','))
      .then((drafts) => setState({ drafts }))
      .catch(() => undefined)
  }, [key])
  useRefresh(refresh)

  if (!key) {
    return (
      <p className="text-sm text-muted-foreground">
        No payments prepared. Select open invoices and choose Pay selected.
      </p>
    )
  }
  if (state === null) {
    return <p className="text-sm text-muted-foreground">Loading payments…</p>
  }
  if ('error' in state) {
    return <p className="text-sm text-destructive">{state.error}</p>
  }

  const { drafts } = state
  const draft = drafts[index]
  if (!draft) {
    return <p className="text-sm text-muted-foreground">These payments no longer exist.</p>
  }

  function replace(updated: PaymentDraft) {
    setState((current) =>
      current && 'drafts' in current
        ? { drafts: current.drafts.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)) }
        : current,
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-center justify-between gap-2">
        <h1 className="text-lg font-semibold">
          Payment {index + 1} of {drafts.length}
        </h1>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={index === 0}
            onClick={() => setIndex(index - 1)}
          >
            Previous
          </Button>
          {index < drafts.length - 1 ? (
            <Button size="sm" onClick={() => setIndex(index + 1)}>
              Next
            </Button>
          ) : (
            <Button size="sm" render={<Link to="/finance/invoices" />}>
              Done
            </Button>
          )}
        </div>
      </header>
      <div
        key={draft.id}
        className="grid grid-cols-1 gap-6 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]"
      >
        <PaymentCard draft={draft} onChange={replace} />
        {draft.attachmentId ? (
          <PdfViewer attachment={{ id: draft.attachmentId, filename: `Invoice for ${draft.payee}` }} />
        ) : (
          <p className="text-sm text-muted-foreground">
            No PDF for this invoice;{' '}
            <Link className="underline" to={`/finance/invoices/${draft.emailId}`}>
              open the email
            </Link>{' '}
            to compare.
          </p>
        )}
      </div>
    </div>
  )
}
