import { type FormEvent, useState } from 'react'

import { InvoiceStatusBadge } from '@/components/finance/InvoiceStatusBadge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api, type Invoice, type InvoiceEdit, type InvoiceField } from '@/lib/api'
import { formatTimestamp } from '@/lib/format'
import { describeApiError } from '@/lib/http'
import { describeIssue } from '@/lib/invoices'

const FIELDS: { name: InvoiceField; label: string; type?: string }[] = [
  { name: 'payee', label: 'Payee' },
  { name: 'iban', label: 'IBAN' },
  { name: 'bic', label: 'BIC' },
  { name: 'amount', label: 'Amount', type: 'text' },
  { name: 'currency', label: 'Currency' },
  { name: 'invoiceNumber', label: 'Invoice number' },
  { name: 'reference', label: 'Reference' },
  { name: 'invoiceDate', label: 'Invoice date', type: 'date' },
  { name: 'dueDate', label: 'Due date', type: 'date' },
]

/** The fields whose form value differs from the invoice; blank means clear. */
function changes(form: FormData, invoice: Invoice): InvoiceEdit {
  const edit: InvoiceEdit = {}
  for (const { name } of FIELDS) {
    let value = String(form.get(name) ?? '').trim()
    if (name === 'amount') {
      // German invoices write 1.234,56; the API takes 1234.56.
      value = value.includes(',') ? value.replace(/\./g, '').replace(',', '.') : value
    }
    const next = value === '' ? null : value
    const current = invoice[name]
    const same = name === 'amount' && next !== null && current !== null
      ? Number(next) === Number(current)
      : next === current
    if (!same) {
      edit[name] = next
    }
  }
  return edit
}

interface Props {
  invoice: Invoice
  onChange: (invoice: Invoice) => void
}

export function InvoiceFields({ invoice, onChange }: Props) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const paidOn = invoice.paidAt ? formatTimestamp(invoice.paidAt) : null

  async function run(action: () => Promise<Invoice>) {
    setSaving(true)
    setError(null)
    try {
      onChange(await action())
    } catch (caught: unknown) {
      setError(describeApiError(caught))
    } finally {
      setSaving(false)
    }
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const edit = changes(new FormData(event.currentTarget), invoice)
    if (Object.keys(edit).length === 0) {
      return
    }
    void run(() => api.updateInvoice(invoice.id, edit))
  }

  function setPaid(paid: boolean) {
    void run(async () => {
      const [updated] = await api.setInvoicesPaid([invoice.id], paid)
      return updated
    })
  }

  return (
    // Keyed on the saved values so the inputs reset to what the server stored.
    <form
      key={JSON.stringify(invoice)}
      onSubmit={save}
      className="flex flex-col gap-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <InvoiceStatusBadge status={invoice.status} />
        {invoice.status === 'paid' && invoice.paidBy === 'owner' ? (
          <span className="text-xs text-muted-foreground">
            Marked paid by you{paidOn ? ` on ${paidOn}` : ''}
          </span>
        ) : null}
      </div>
      {invoice.issues.length > 0 ? (
        <ul className="list-disc pl-5 text-sm text-amber-700 dark:text-amber-400">
          {invoice.issues.map((issue) => (
            <li key={issue}>{describeIssue(issue)}</li>
          ))}
        </ul>
      ) : null}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        {FIELDS.map(({ name, label, type }) => (
          <Label key={name} className="flex-col items-start gap-1 text-xs text-muted-foreground">
            {label}
            <Input
              name={name}
              type={type ?? 'text'}
              defaultValue={invoice[name] ?? ''}
              inputMode={name === 'amount' ? 'decimal' : undefined}
              className="text-foreground"
            />
          </Label>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" size="sm" disabled={saving}>
          Save
        </Button>
        {invoice.status === 'paid' ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={saving}
            onClick={() => setPaid(false)}
          >
            Mark unpaid
          </Button>
        ) : (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={saving}
            onClick={() => setPaid(true)}
          >
            Mark paid
          </Button>
        )}
        {error ? <span className="text-sm text-destructive">{error}</span> : null}
      </div>
    </form>
  )
}
