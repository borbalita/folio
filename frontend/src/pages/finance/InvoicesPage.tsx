import { useEffect, useState } from 'react'

import { InvoiceList } from '@/components/finance/InvoiceList'
import { api, type InvoiceSummary } from '@/lib/api'
import { describeApiError } from '@/lib/http'

type State = { invoices: InvoiceSummary[] } | { error: string } | null

export function InvoicesPage() {
  const [state, setState] = useState<State>(null)

  useEffect(() => {
    let cancelled = false
    api
      .listInvoices()
      .then((invoices) => {
        if (!cancelled) {
          setState({ invoices })
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
  }, [])

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
      <h1 className="text-lg font-semibold">Invoices</h1>
      {state === null ? <p className="text-sm text-muted-foreground">Loading invoices…</p> : null}
      {state && 'error' in state ? (
        <p className="text-sm text-destructive">{state.error}</p>
      ) : null}
      {state && 'invoices' in state && state.invoices.length === 0 ? (
        <p className="text-sm text-muted-foreground">No invoices.</p>
      ) : null}
      {state && 'invoices' in state && state.invoices.length > 0 ? (
        <InvoiceList invoices={state.invoices} />
      ) : null}
    </div>
  )
}
