import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { describeApiError } from '@/lib/http'

export function ResetBlock({ onReset }: { onReset: () => void }) {
  const [confirming, setConfirming] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  async function reset() {
    setResetting(true)
    setMessage(null)
    try {
      await api.resetDemo()
      setMessage('The demo is back to its base state.')
      onReset()
    } catch (caught: unknown) {
      setMessage(describeApiError(caught))
    } finally {
      setResetting(false)
      setConfirming(false)
    }
  }

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-border p-4">
      <h2 className="font-heading text-base font-semibold">Reset demo</h2>
      <p className="text-sm text-muted-foreground">
        Deletes everything the demo created and restores the base state, dated from today.
      </p>
      {confirming ? (
        <div className="flex gap-2">
          <Button variant="destructive" disabled={resetting} onClick={() => void reset()}>
            {resetting ? 'Resetting…' : 'Yes, reset'}
          </Button>
          <Button variant="outline" disabled={resetting} onClick={() => setConfirming(false)}>
            Cancel
          </Button>
        </div>
      ) : (
        <Button variant="outline" onClick={() => setConfirming(true)}>
          Reset demo
        </Button>
      )}
      {message ? <p className="text-sm">{message}</p> : null}
    </section>
  )
}
