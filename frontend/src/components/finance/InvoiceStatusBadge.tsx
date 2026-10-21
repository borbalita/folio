import type { DisplayStatus } from '@/lib/api'
import { STATUS_LABELS } from '@/lib/invoices'

const STYLES: Record<DisplayStatus, string> = {
  open: 'bg-primary/10 text-primary',
  pending: 'bg-sky-500/15 text-sky-700 dark:text-sky-400',
  needs_info: 'bg-amber-500/15 text-amber-700 dark:text-amber-400',
  paid: 'bg-muted text-muted-foreground',
}

export function InvoiceStatusBadge({ status }: { status: DisplayStatus }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STYLES[status]}`}>
      {STATUS_LABELS[status]}
    </span>
  )
}
