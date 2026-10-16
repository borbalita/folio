import { useEffect, useMemo, useState } from 'react'

import { InvoiceFilters } from '@/components/finance/InvoiceFilters'
import { InvoiceList } from '@/components/finance/InvoiceList'
import { PayInvoices } from '@/components/finance/PayInvoices'
import { Button } from '@/components/ui/button'
import { api, type InvoiceRow } from '@/lib/api'
import { describeApiError } from '@/lib/http'
import { DEFAULT_FILTERS, type Filters, isOverdue, todayIso } from '@/lib/invoices'

type State = { invoices: InvoiceRow[] } | { error: string } | null

/** The invoice date, or the day the email arrived when the invoice shows none. */
function dayOf(invoice: InvoiceRow): string {
  return invoice.invoiceDate ?? invoice.email.sentAt.slice(0, 10)
}

function visible(invoices: InvoiceRow[], filters: Filters, today: string): InvoiceRow[] {
  const payee = filters.payee.trim().toLowerCase()
  const shown = invoices.filter(
    (invoice) =>
      filters.statuses.includes(invoice.status) &&
      (!filters.from || dayOf(invoice) >= filters.from) &&
      (!filters.to || dayOf(invoice) <= filters.to) &&
      (!payee || (invoice.payee ?? '').toLowerCase().includes(payee)),
  )
  // Overdue first, oldest due date first; the rest keep the server's newest-first order.
  const overdue = shown
    .filter((invoice) => isOverdue(invoice, today))
    .sort((a, b) => (a.dueDate ?? '').localeCompare(b.dueDate ?? ''))
  return [...overdue, ...shown.filter((invoice) => !isOverdue(invoice, today))]
}

export function InvoicesPage() {
  const [state, setState] = useState<State>(null)
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [saving, setSaving] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const today = todayIso()

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

  const all = state && 'invoices' in state ? state.invoices : null
  const shown = useMemo(() => (all ? visible(all, filters, today) : []), [all, filters, today])
  const chosen = shown.filter((invoice) => selected.has(invoice.id))

  function toggleAll(checked: boolean) {
    setSelected(checked ? new Set(shown.map((invoice) => invoice.id)) : new Set())
  }

  function toggle(id: string, checked: boolean) {
    setSelected((current) => {
      const next = new Set(current)
      if (checked) {
        next.add(id)
      } else {
        next.delete(id)
      }
      return next
    })
  }

  async function markPaid(paid: boolean) {
    setSaving(true)
    setActionError(null)
    try {
      const updated = await api.setInvoicesPaid(
        chosen.map((invoice) => invoice.id),
        paid,
      )
      const byId = new Map(updated.map((invoice) => [invoice.id, invoice]))
      setState((current) =>
        current && 'invoices' in current
          ? {
              invoices: current.invoices.map((invoice) => {
                const fresh = byId.get(invoice.id)
                return fresh ? { ...fresh, email: invoice.email } : invoice
              }),
            }
          : current,
      )
      setSelected(new Set())
    } catch (caught: unknown) {
      setActionError(describeApiError(caught))
    } finally {
      setSaving(false)
    }
  }

  const openChosen = chosen.filter((invoice) => invoice.status === 'open')

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-4">
      <h1 className="text-lg font-semibold">Invoices</h1>
      <InvoiceFilters filters={filters} onChange={setFilters} />
      <div className="flex flex-wrap items-center gap-2">
        <PayInvoices
          invoiceIds={openChosen.map((invoice) => invoice.id)}
          label="Pay selected"
          skipped={chosen.length - openChosen.length}
        />
        <Button
          size="sm"
          variant="outline"
          disabled={saving || chosen.length === 0}
          onClick={() => void markPaid(true)}
        >
          Mark paid
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={saving || chosen.length === 0}
          onClick={() => void markPaid(false)}
        >
          Mark unpaid
        </Button>
        <span className="text-xs text-muted-foreground">
          {chosen.length > 0 ? `${chosen.length} selected` : null}
        </span>
        {actionError ? <span className="text-sm text-destructive">{actionError}</span> : null}
      </div>
      {state === null ? <p className="text-sm text-muted-foreground">Loading invoices…</p> : null}
      {state && 'error' in state ? (
        <p className="text-sm text-destructive">{state.error}</p>
      ) : null}
      {all && shown.length === 0 ? (
        <p className="text-sm text-muted-foreground">No invoices match.</p>
      ) : null}
      {shown.length > 0 ? (
        <InvoiceList
          invoices={shown}
          today={today}
          selected={selected}
          onToggle={toggle}
          onToggleAll={toggleAll}
        />
      ) : null}
    </div>
  )
}
