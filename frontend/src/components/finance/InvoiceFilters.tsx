import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { InvoiceStatus } from '@/lib/api'
import { type Filters, STATUS_LABELS } from '@/lib/invoices'

const STATUSES: InvoiceStatus[] = ['open', 'needs_info', 'paid']

interface Props {
  filters: Filters
  onChange: (filters: Filters) => void
}

export function InvoiceFilters({ filters, onChange }: Props) {
  function toggleStatus(status: InvoiceStatus, checked: boolean) {
    const statuses = checked
      ? [...filters.statuses, status]
      : filters.statuses.filter((item) => item !== status)
    onChange({ ...filters, statuses })
  }

  return (
    <div className="flex flex-wrap items-end gap-4">
      <fieldset className="flex items-center gap-3">
        <legend className="sr-only">Status</legend>
        {STATUSES.map((status) => (
          <Label key={status} className="font-normal">
            <Checkbox
              checked={filters.statuses.includes(status)}
              onCheckedChange={(checked) => toggleStatus(status, checked)}
            />
            {STATUS_LABELS[status]}
          </Label>
        ))}
      </fieldset>
      <Label className="flex-col items-start gap-1 text-xs font-normal text-muted-foreground">
        From
        <Input
          type="date"
          value={filters.from}
          onChange={(event) => onChange({ ...filters, from: event.target.value })}
        />
      </Label>
      <Label className="flex-col items-start gap-1 text-xs font-normal text-muted-foreground">
        To
        <Input
          type="date"
          value={filters.to}
          onChange={(event) => onChange({ ...filters, to: event.target.value })}
        />
      </Label>
      <Label className="flex-col items-start gap-1 text-xs font-normal text-muted-foreground">
        Payee
        <Input
          type="search"
          placeholder="Search payee"
          value={filters.payee}
          onChange={(event) => onChange({ ...filters, payee: event.target.value })}
        />
      </Label>
    </div>
  )
}
