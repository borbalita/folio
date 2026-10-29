import { type FormEvent, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  api,
  type ApprovedPayment,
  type PaymentCorrection,
  type PaymentDraft,
} from '@/lib/api'
import { describeApiError } from '@/lib/http'
import { formatAmount, parseAmount } from '@/lib/invoices'

type FieldName = keyof PaymentCorrection

const FIELDS: { name: FieldName; label: string }[] = [
  { name: 'payee', label: 'Payee' },
  { name: 'iban', label: 'IBAN' },
  { name: 'bic', label: 'BIC' },
  { name: 'amount', label: 'Amount' },
  { name: 'reference', label: 'Reference' },
]

/** The fields whose form value differs from the draft; blank means clear. */
function corrections(form: FormData, draft: PaymentDraft): PaymentCorrection {
  const correction: Record<string, string | null> = {}
  for (const { name } of FIELDS) {
    let value = String(form.get(name) ?? '').trim()
    if (name === 'amount') {
      value = parseAmount(value)
    }
    const next = value === '' ? null : value
    const current = draft[name]
    const same = name === 'amount' && next !== null
      ? Number(next) === Number(current)
      : next === (current || null)
    if (!same) {
      correction[name] = next
    }
  }
  return correction
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-mono text-sm">{value ?? '—'}</dd>
    </div>
  )
}

interface Props {
  draft: PaymentDraft
  onChange: (draft: PaymentDraft) => void
}

/** One payment to check against its invoice and correct, then pay by scanning the QR code. */
export function PaymentCard({ draft, onChange }: Props) {
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

  function approve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const correction = corrections(new FormData(event.currentTarget), draft)
    void run(() => api.approvePaymentDraft(draft.id, correction), setApproved)
  }

  const amount = formatAmount(draft.amount, draft.currency) ?? draft.amount
  const closed = draft.status === 'cancelled' || draft.status === 'completed'

  return (
    <section className="flex flex-col gap-4 rounded-md border border-border p-4">
      <p className="text-3xl font-semibold tabular-nums">{amount}</p>

      {closed || approved ? (
        <dl className="flex flex-col gap-1">
          {FIELDS.map(({ name, label }) => (
            <Field key={name} label={label} value={draft[name]} />
          ))}
        </dl>
      ) : null}

      {closed ? (
        <p className="text-sm text-muted-foreground">This payment is {draft.status}.</p>
      ) : approved ? (
        <div className="flex flex-col items-center gap-2">
          <img src={approved.qr} alt="GiroCode for this payment" className="size-56" />
          <p className="text-center text-xs text-muted-foreground">
            Scan this in your banking app and confirm the transfer there. The invoice
            turns paid when the payment shows up in the next bank sync.
          </p>
        </div>
      ) : (
        <form className="flex flex-col gap-3" onSubmit={approve}>
          <div className="flex flex-col gap-2">
            {FIELDS.map(({ name, label }) => (
              <div key={name} className="flex flex-col gap-1">
                <Label htmlFor={`${draft.id}-${name}`}>{label}</Label>
                <Input
                  id={`${draft.id}-${name}`}
                  name={name}
                  defaultValue={draft[name] ?? ''}
                  className="font-mono"
                  disabled={busy}
                />
              </div>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            Corrections are saved to the invoice when you approve.
          </p>
          <div className="flex gap-2">
            <Button type="submit" disabled={busy}>
              Approve
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => void run(() => api.cancelPaymentDraft(draft.id))}
            >
              Cancel payment
            </Button>
          </div>
        </form>
      )}

      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </section>
  )
}
