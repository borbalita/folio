import { Link } from 'react-router-dom'

import { InvoiceStatusBadge } from '@/components/finance/InvoiceStatusBadge'
import { Checkbox } from '@/components/ui/checkbox'
import type { InvoiceRow } from '@/lib/api'
import { formatIsoDay } from '@/lib/format'
import { formatAmount, isOverdue } from '@/lib/invoices'

interface Props {
  invoices: InvoiceRow[]
  today: string
  selected: Set<string>
  onToggle: (id: string, checked: boolean) => void
}

export function InvoiceList({ invoices, today, selected, onToggle }: Props) {
  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-muted-foreground">
          <tr className="border-b border-border">
            <th className="w-8 px-3 py-2">
              <span className="sr-only">Select</span>
            </th>
            <th className="px-3 py-2 font-medium">Payee</th>
            <th className="px-3 py-2 font-medium">Invoice no.</th>
            <th className="px-3 py-2 text-right font-medium">Amount</th>
            <th className="px-3 py-2 font-medium">Due</th>
            <th className="px-3 py-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {invoices.map((invoice) => {
            const overdue = isOverdue(invoice, today)
            const link = `/finance/invoices/${invoice.emailId}`
            return (
              <tr key={invoice.id} className="hover:bg-muted/60">
                <td className="px-3 py-2">
                  <Checkbox
                    aria-label={`Select ${invoice.payee ?? invoice.email.subject}`}
                    checked={selected.has(invoice.id)}
                    onCheckedChange={(checked) => onToggle(invoice.id, checked)}
                  />
                </td>
                <td className="max-w-64 px-3 py-2">
                  <Link to={link} className="flex flex-col hover:underline">
                    <span className="truncate">{invoice.payee ?? invoice.email.from}</span>
                    <span className="truncate text-xs text-muted-foreground">
                      {invoice.email.subject || '(no subject)'}
                    </span>
                  </Link>
                </td>
                <td className="px-3 py-2">{invoice.invoiceNumber ?? '—'}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatAmount(invoice.amount, invoice.currency) ?? '—'}
                </td>
                <td className={`px-3 py-2 ${overdue ? 'font-medium text-destructive' : ''}`}>
                  {formatIsoDay(invoice.dueDate ?? undefined) ?? '—'}
                  {overdue ? ' · overdue' : ''}
                </td>
                <td className="px-3 py-2">
                  <InvoiceStatusBadge status={invoice.status} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
