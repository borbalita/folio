import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { api, type Invoice, type InvoiceMatch, type MatchSignal } from '@/lib/api'
import { formatIsoDay } from '@/lib/format'
import { describeApiError } from '@/lib/http'
import { formatAmount } from '@/lib/invoices'

const SIGNAL_LABELS: Record<MatchSignal, string> = {
  amount: 'amount',
  iban: 'IBAN',
  reference: 'invoice number in the transfer text',
  name: 'payee name',
}

function Transaction({ match }: { match: InvoiceMatch }) {
  const { transaction } = match
  return (
    <div className="flex flex-col text-sm">
      <span>
        {formatIsoDay(transaction.date) ?? transaction.date} · {transaction.bank} ·{' '}
        {transaction.counterparty ?? 'Unknown payee'}
      </span>
      <span className="text-xs text-muted-foreground">
        {formatAmount(transaction.amount, transaction.currency)} · same{' '}
        {match.signals.map((signal) => SIGNAL_LABELS[signal]).join(', ')}
      </span>
    </div>
  )
}

interface Props {
  invoice: Invoice
  onChange: (invoice: Invoice) => void
}

/** The bank transaction that paid this invoice, or the ones that might have. */
export function InvoicePayment({ invoice, onChange }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run(action: () => Promise<Invoice>) {
    setBusy(true)
    setError(null)
    try {
      onChange(await action())
    } catch (caught: unknown) {
      setError(describeApiError(caught))
    } finally {
      setBusy(false)
    }
  }

  const { match, suggestions } = invoice
  if (!match && suggestions.length === 0 && invoice.status !== 'open') {
    return null
  }

  return (
    <section className="flex flex-col gap-3 rounded-md border border-border p-4">
      <h3 className="text-sm font-medium">Payment</h3>

      {match ? (
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium text-muted-foreground">
            {match.source === 'auto' ? 'Matched automatically' : 'Confirmed by you'}
          </p>
          <Transaction match={match} />
          <div>
            <Button
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => void run(() => api.rejectMatch(match.id))}
            >
              Not this payment
            </Button>
          </div>
        </div>
      ) : null}

      {!match && suggestions.length === 0 ? (
        <p className="text-sm text-muted-foreground">No matching payment found yet.</p>
      ) : null}

      {!match && suggestions.length > 0 ? (
        <ul className="flex flex-col gap-3">
          <li className="text-xs text-muted-foreground">
            {suggestions.length === 1 ? 'Possible payment' : 'Possible payments'}
          </li>
          {suggestions.map((suggestion) => (
            <li key={suggestion.id} className="flex flex-col gap-2">
              <Transaction match={suggestion} />
              <div className="flex gap-2">
                <Button
                  size="sm"
                  disabled={busy}
                  onClick={() => void run(() => api.confirmMatch(suggestion.id))}
                >
                  Confirm
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  onClick={() => void run(() => api.rejectMatch(suggestion.id))}
                >
                  Reject
                </Button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </section>
  )
}
