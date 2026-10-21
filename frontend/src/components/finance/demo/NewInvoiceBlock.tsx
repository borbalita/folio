import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { api, type DemoInvoiceKind, type DemoSendResult } from '@/lib/api'
import { describeApiError } from '@/lib/http'
import { formatAmount, STATUS_LABELS } from '@/lib/invoices'

const KINDS: { kind: DemoInvoiceKind; label: string }[] = [
  { kind: 'normal', label: 'Normal' },
  { kind: 'already_paid', label: 'Already paid' },
  { kind: 'online_only', label: 'Online only' },
  { kind: 'random', label: 'Random' },
]

interface LogEntry {
  at: string
  result: DemoSendResult | null
  error: string | null
}

function outcome(entry: LogEntry): string {
  if (entry.error) {
    return entry.error
  }
  const result = entry.result
  if (!result) {
    return ''
  }
  const statuses = result.invoices.map((invoice) => STATUS_LABELS[invoice.status]).join(', ')
  return result.error ?? (statuses || 'Not recognised as an invoice')
}

export function NewInvoiceBlock() {
  const [kind, setKind] = useState<DemoInvoiceKind>('normal')
  const [sending, setSending] = useState(false)
  const [log, setLog] = useState<LogEntry[]>([])

  async function send() {
    setSending(true)
    const at = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    try {
      const result = await api.sendDemoInvoice(kind)
      setLog((current) => [{ at, result, error: null }, ...current].slice(0, 5))
    } catch (caught: unknown) {
      setLog((current) => [{ at, result: null, error: describeApiError(caught) }, ...current].slice(0, 5))
    } finally {
      setSending(false)
    }
  }

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-border p-4">
      <h2 className="font-heading text-base font-semibold">New invoice</h2>
      <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Invoice kind">
        {KINDS.map((option) => (
          <Button
            key={option.kind}
            type="button"
            role="radio"
            aria-checked={kind === option.kind}
            variant={kind === option.kind ? 'default' : 'outline'}
            onClick={() => setKind(option.kind)}
          >
            {option.label}
          </Button>
        ))}
      </div>
      <Button onClick={() => void send()} disabled={sending}>
        {sending ? 'Sending… (about 20 s)' : 'Send'}
      </Button>
      {log.length > 0 ? (
        <ul className="flex flex-col gap-2 text-sm">
          {log.map((entry, index) => (
            <li key={`${entry.at}-${index}`} className="flex flex-col">
              <span className="text-muted-foreground">
                {entry.at}
                {entry.result
                  ? ` · ${entry.result.sent.vendor} · ${formatAmount(entry.result.sent.amount, 'EUR') ?? ''}`
                  : ''}
              </span>
              <span className={entry.error || entry.result?.error ? 'text-destructive' : undefined}>
                {outcome(entry)}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}
