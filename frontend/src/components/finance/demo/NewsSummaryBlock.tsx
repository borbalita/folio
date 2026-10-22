import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { describeApiError } from '@/lib/http'

export function NewsSummaryBlock() {
  const [sending, setSending] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  async function send() {
    setSending(true)
    setMessage(null)
    try {
      const result = await api.sendDemoNewsSummary()
      setMessage(`Sent: ${result.headline}`)
    } catch (caught: unknown) {
      setMessage(describeApiError(caught))
    } finally {
      setSending(false)
    }
  }

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-border p-4">
      <h2 className="font-heading text-base font-semibold">News</h2>
      <p className="text-sm text-muted-foreground">
        Summarises the most covered big story and posts it to your Telegram chat.
      </p>
      <Button variant="outline" disabled={sending} onClick={() => void send()}>
        {sending ? 'Sending…' : 'Send news summary to Telegram'}
      </Button>
      {message ? <p className="text-sm">{message}</p> : null}
    </section>
  )
}
