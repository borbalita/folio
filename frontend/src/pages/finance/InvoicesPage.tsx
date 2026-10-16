import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { InvoiceFilters } from '@/components/finance/InvoiceFilters'
import { InvoiceList } from '@/components/finance/InvoiceList'
import { Button } from '@/components/ui/button'
import { api, type BankAccount, type BankName, type InvoiceRow } from '@/lib/api'
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
  const navigate = useNavigate()
  const [payFrom, setPayFrom] = useState<{ bank: BankName; account: BankAccount }[] | null>(null)
  const [accountId, setAccountId] = useState('')

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

  async function choosePayFrom() {
    setActionError(null)
    try {
      const connections = await api.listBankConnections()
      // Only accounts with an IBAN can send a SEPA transfer; PayPal has none.
      const accounts = connections
        .filter((connection) => connection.connected)
        .flatMap((connection) =>
          connection.accounts
            .filter((account) => account.ibanMasked)
            .map((account) => ({ bank: connection.bank, account })),
        )
      if (accounts.length === 0) {
        setActionError('Connect a bank account with an IBAN on the Accounts page first.')
        return
      }
      setPayFrom(accounts)
      setAccountId(accounts[0].account.id)
    } catch (caught: unknown) {
      setActionError(describeApiError(caught))
    }
  }

  async function prepare() {
    setSaving(true)
    setActionError(null)
    try {
      const open = chosen.filter((invoice) => invoice.status === 'open')
      const result = await api.createPaymentDrafts(
        open.map((invoice) => invoice.id),
        accountId,
      )
      if (result.drafts.length === 0) {
        setActionError('None of the selected invoices is open, so there is nothing to pay.')
        return
      }
      navigate(`/finance/payments?drafts=${result.drafts.map((draft) => draft.id).join(',')}`)
    } catch (caught: unknown) {
      setActionError(describeApiError(caught))
    } finally {
      setSaving(false)
    }
  }

  const openChosen = chosen.filter((invoice) => invoice.status === 'open').length
  const notOpen = chosen.length - openChosen

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-4">
      <h1 className="text-lg font-semibold">Invoices</h1>
      <InvoiceFilters filters={filters} onChange={setFilters} />
      <div className="flex items-center gap-2">
        <Button
          size="sm"
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
        <Button
          size="sm"
          variant="outline"
          disabled={saving || openChosen === 0}
          onClick={() => void choosePayFrom()}
        >
          Pay selected
        </Button>
        <span className="text-xs text-muted-foreground">
          {chosen.length > 0 ? `${chosen.length} selected` : null}
        </span>
        {actionError ? <span className="text-sm text-destructive">{actionError}</span> : null}
      </div>
      {payFrom && openChosen > 0 ? (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-border p-3 text-sm">
          <label htmlFor="pay-from">Pay {openChosen} from</label>
          <select
            id="pay-from"
            className="rounded-md border border-border bg-background px-2 py-1"
            value={accountId}
            onChange={(event) => setAccountId(event.target.value)}
          >
            {payFrom.map(({ bank, account }) => (
              <option key={account.id} value={account.id}>
                {bank}
                {account.name ? ` · ${account.name}` : ''} · {account.ibanMasked}
              </option>
            ))}
          </select>
          <Button size="sm" disabled={saving || !accountId} onClick={() => void prepare()}>
            Prepare payments
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setPayFrom(null)}>
            Close
          </Button>
          {notOpen > 0 ? (
            <span className="text-xs text-muted-foreground">
              {notOpen} selected invoice{notOpen === 1 ? ' is' : 's are'} not open and will be
              skipped.
            </span>
          ) : null}
        </div>
      ) : null}
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
