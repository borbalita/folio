import { Link } from 'react-router-dom'

import type { InvoiceSummary } from '@/lib/api'
import { formatTimestamp } from '@/lib/format'

export function InvoiceList({ invoices }: { invoices: InvoiceSummary[] }) {
  return (
    <ul className="flex flex-col divide-y divide-border rounded-md border border-border">
      {invoices.map((invoice) => {
        const sent = formatTimestamp(invoice.sentAt)
        return (
          <li key={invoice.id}>
            <Link
              to={`/finance/invoices/${invoice.id}`}
              className="flex flex-col px-3 py-2 text-sm hover:bg-muted/60"
            >
              <span className="truncate">{invoice.subject || '(no subject)'}</span>
              <span className="truncate text-xs text-muted-foreground">
                {invoice.from}
                {sent ? ` · ${sent}` : ''}
              </span>
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
