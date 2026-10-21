import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { BookPaymentsBlock } from '@/components/finance/demo/BookPaymentsBlock'
import { NewInvoiceBlock } from '@/components/finance/demo/NewInvoiceBlock'
import { ResetBlock } from '@/components/finance/demo/ResetBlock'
import { api, type DemoPayment } from '@/lib/api'
import { ApiError, describeApiError } from '@/lib/http'

type State = { payments: DemoPayment[] } | { denied: true } | { error: string } | null

/** The demo's controls, for the presenter's phone or second tab. Not linked from the app. */
export function DemoPresenterPage() {
  const [state, setState] = useState<State>(null)
  const [generation, setGeneration] = useState(0)

  useEffect(() => {
    let cancelled = false
    api
      .listDemoPayments()
      .then((payments) => {
        if (!cancelled) {
          setState({ payments })
        }
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return
        }
        // The server decides who the demo user is: 403 for anyone else, 404 without a demo.
        if (caught instanceof ApiError && (caught.status === 403 || caught.status === 404)) {
          setState({ denied: true })
        } else {
          setState({ error: describeApiError(caught) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [generation])

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col gap-4 p-4">
      <header className="flex items-center justify-between">
        <h1 className="font-heading text-lg font-semibold">Demo controls</h1>
        <Link to="/finance" className="text-sm text-muted-foreground hover:underline">
          Open Finance
        </Link>
      </header>
      {state === null ? <p className="text-sm text-muted-foreground">Loading…</p> : null}
      {state && 'denied' in state ? (
        <p className="text-sm text-muted-foreground">This page is only for the demo account.</p>
      ) : null}
      {state && 'error' in state ? <p className="text-sm text-destructive">{state.error}</p> : null}
      {state && 'payments' in state ? (
        <>
          <NewInvoiceBlock />
          {/* Remounted after a reset, so the list starts from the fresh payments. */}
          <BookPaymentsBlock key={generation} initial={state.payments} />
          <ResetBlock onReset={() => setGeneration((value) => value + 1)} />
        </>
      ) : null}
    </main>
  )
}
