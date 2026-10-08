import { NavLink } from 'react-router-dom'

import type { InvoiceSummary } from '@/lib/api'
import { formatTimestamp } from '@/lib/format'

interface InvoiceListProps {
  invoices: InvoiceSummary[]
  error: string | null
}

export function InvoiceList({ invoices, error }: InvoiceListProps) {
  return (
    <section className="flex flex-col gap-0.5 border-b border-sidebar-border p-2">
      <h2 className="px-2 pb-1 text-xs font-medium text-muted-foreground">Invoices</h2>
      {error ? <p className="px-2 py-1 text-sm text-destructive">{error}</p> : null}
      {!error && invoices.length === 0 ? (
        <p className="px-2 py-1 text-sm text-muted-foreground">No invoices.</p>
      ) : null}
      {invoices.map((invoice) => (
        <NavLink
          key={invoice.id}
          to={`/email/invoices/${invoice.id}`}
          className={({ isActive }) =>
            [
              'flex flex-col rounded-md px-2 py-1.5 text-sm',
              isActive
                ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                : 'hover:bg-sidebar-accent/60',
            ].join(' ')
          }
        >
          <span className="truncate">{invoice.subject || '(no subject)'}</span>
          <span className="truncate text-xs text-muted-foreground">
            {invoice.from}
            {formatTimestamp(invoice.sentAt) ? ` · ${formatTimestamp(invoice.sentAt)}` : ''}
          </span>
        </NavLink>
      ))}
    </section>
  )
}
