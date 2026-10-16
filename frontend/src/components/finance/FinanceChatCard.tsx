import { useEffect, useState } from 'react'

import { InvoiceList } from '@/components/finance/InvoiceList'
import { PayInvoices } from '@/components/finance/PayInvoices'
import { PaymentCard } from '@/components/finance/PaymentCard'
import { api, type InvoiceRow, type PaymentDraft } from '@/lib/api'
import type { FinanceCardData } from '@/lib/chat-messages'
import { todayIso } from '@/lib/invoices'

type Loaded<T> = { items: T[] } | { error: true } | null

function Note({ children }: { children: string }) {
  return <p className="text-xs text-muted-foreground">{children}</p>
}

/** Invoices named in an answer, shown as they are now, not as they were when answered. */
function InvoicesCard({ ids }: { ids: string[] }) {
  const [state, setState] = useState<Loaded<InvoiceRow>>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false
    api
      .listInvoices()
      .then((all) => {
        if (!cancelled) {
          const byId = new Map(all.map((invoice) => [invoice.id, invoice]))
          setState({ items: ids.flatMap((id) => byId.get(id) ?? []) })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState({ error: true })
        }
      })
    return () => {
      cancelled = true
    }
  }, [ids])

  if (state === null) {
    return <Note>Loading invoices…</Note>
  }
  if ('error' in state) {
    return <Note>These invoices could not be loaded.</Note>
  }
  const missing = ids.length - state.items.length
  const openChosen = state.items.filter(
    (invoice) => selected.has(invoice.id) && invoice.status === 'open',
  )
  return (
    <div className="flex flex-col gap-2">
      {state.items.length > 0 ? (
        <InvoiceList
          invoices={state.items}
          today={todayIso()}
          selected={selected}
          onToggle={(id, checked) =>
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
          onToggleAll={(checked) =>
            setSelected(checked ? new Set(state.items.map((invoice) => invoice.id)) : new Set())
          }
        />
      ) : null}
      {missing > 0 ? (
        <Note>{`${missing} ${missing === 1 ? 'invoice is' : 'invoices are'} no longer available.`}</Note>
      ) : null}
      {state.items.some((invoice) => invoice.status === 'open') ? (
        <div className="flex gap-2">
          <PayInvoices invoiceIds={openChosen.map((invoice) => invoice.id)} label="Pay selected" />
        </div>
      ) : null}
    </div>
  )
}

/** Payments prepared in chat. Approving happens here, by the owner, never by the model. */
function PaymentsCard({ ids }: { ids: string[] }) {
  const [state, setState] = useState<Loaded<PaymentDraft>>(null)

  useEffect(() => {
    let cancelled = false
    api
      .getPaymentDrafts(ids)
      .then((drafts) => {
        if (!cancelled) {
          setState({ items: drafts })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState({ error: true })
        }
      })
    return () => {
      cancelled = true
    }
  }, [ids])

  if (state === null) {
    return <Note>Loading payments…</Note>
  }
  if ('error' in state) {
    return <Note>These payments are no longer available.</Note>
  }
  return (
    <div className="flex flex-col gap-3">
      {state.items.map((draft) => (
        <PaymentCard
          key={draft.id}
          draft={draft}
          onChange={(next) =>
            setState((current) =>
              current && 'items' in current
                ? { items: current.items.map((item) => (item.id === next.id ? next : item)) }
                : current,
            )
          }
        />
      ))}
    </div>
  )
}

export function FinanceChatCard({ card }: { card: FinanceCardData }) {
  return card.kind === 'invoices' ? <InvoicesCard ids={card.ids} /> : <PaymentsCard ids={card.ids} />
}
