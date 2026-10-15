import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { api, type ApprovedPayment, type PaymentDraft } from '@/lib/api'
import { describeApiError } from '@/lib/http'
import { formatAmount } from '@/lib/invoices'

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="flex items-center gap-2 font-mono text-sm">
        <span>{value ?? '—'}</span>
        {value ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void navigator.clipboard.writeText(value)}
          >
            Copy
          </Button>
        ) : null}
      </dd>
    </div>
  )
}

interface Props {
  draft: PaymentDraft
  onChange: (draft: PaymentDraft) => void
}

/** One payment to check against its invoice, then pay by scanning the QR code. */
export function PaymentCard({ draft, onChange }: Props) {
  const [checked, setChecked] = useState(false)
  const [approved, setApproved] = useState<ApprovedPayment | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run<T extends PaymentDraft>(action: () => Promise<T>, then?: (result: T) => void) {
    setBusy(true)
    setError(null)
    try {
      const result = await action()
      onChange(result)
      then?.(result)
    } catch (caught: unknown) {
      setError(describeApiError(caught))
    } finally {
      setBusy(false)
    }
  }

  const amount = formatAmount(draft.amount, draft.currency) ?? draft.amount
  const from = `${draft.account.bank}${draft.account.name ? ` · ${draft.account.name}` : ''}`
  const closed = draft.status === 'cancelled' || draft.status === 'completed'

  return (
    <section className="flex flex-col gap-4 rounded-md border border-border p-4">
      <p className="text-3xl font-semibold tabular-nums">{amount}</p>
      <dl className="flex flex-col gap-1">
        <Field label="Payee" value={draft.payee} />
        <Field label="IBAN" value={draft.iban} />
        <Field label="BIC" value={draft.bic} />
        <Field label="Amount" value={draft.amount} />
        <Field label="Reference" value={draft.reference} />
        <div className="flex items-center justify-between gap-3">
          <dt className="text-xs text-muted-foreground">From</dt>
          <dd className="text-sm">{from}</dd>
        </div>
      </dl>

      {closed ? (
        <p className="text-sm text-muted-foreground">This payment is {draft.status}.</p>
      ) : approved ? (
        <div className="flex flex-col items-center gap-2">
          <img src={approved.qr} alt="GiroCode for this payment" className="size-56" />
          <p className="text-center text-xs text-muted-foreground">
            Scan this in your {draft.account.bank} app and confirm the transfer there. The invoice
            turns paid when the payment shows up in the next bank sync.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <label className="flex items-start gap-2 text-sm">
            <Checkbox
              checked={checked}
              onCheckedChange={(value) => setChecked(value)}
              aria-label="I checked payee, IBAN, amount and reference against the invoice"
            />
            <span>I checked payee, IBAN, amount and reference against the invoice.</span>
          </label>
          <div className="flex gap-2">
            <Button
              disabled={!checked || busy}
              onClick={() => void run(() => api.approvePaymentDraft(draft.id), setApproved)}
            >
              Approve
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => void run(() => api.cancelPaymentDraft(draft.id))}
            >
              Cancel payment
            </Button>
          </div>
        </div>
      )}

      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </section>
  )
}
