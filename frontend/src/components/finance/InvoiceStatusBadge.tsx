import type { InvoiceStatus } from '@/lib/api'
import { STATUS_LABELS } from '@/lib/invoices'

const STYLES: Record<InvoiceStatus, string> = {
  open: 'bg-primary/10 text-primary',
  needs_info: 'bg-amber-500/15 text-amber-700 dark:text-amber-400',
  paid: 'bg-muted text-muted-foreground',
}

export function InvoiceStatusBadge({ status }: { status: InvoiceStatus }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STYLES[status]}`}>
      {STATUS_LABELS[status]}
    </span>
  )
}
