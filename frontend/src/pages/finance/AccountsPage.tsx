import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { api, type BankConnection, type BankName } from '@/lib/api'
import { formatTimestamp } from '@/lib/format'
import { describeApiError } from '@/lib/http'

type State = { connections: BankConnection[] } | { error: string } | null

export function AccountsPage() {
  const [state, setState] = useState<State>(null)
  const [starting, setStarting] = useState<BankName | null>(null)
  const [startError, setStartError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .listBankConnections()
      .then((connections) => {
        if (!cancelled) {
          setState({ connections })
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setState({ error: describeApiError(caught) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    // Back from the bank page can restore this page from bfcache with `starting` still set.
    function onPageShow(event: PageTransitionEvent) {
      if (event.persisted) {
        setStarting(null)
      }
    }
    window.addEventListener('pageshow', onPageShow)
    return () => window.removeEventListener('pageshow', onPageShow)
  }, [])

  async function start(bank: BankName) {
    setStarting(bank)
    setStartError(null)
    try {
      const { url } = await api.startBankConnection(bank)
      window.location.assign(url)
    } catch (caught: unknown) {
      setStartError(describeApiError(caught))
      setStarting(null)
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
      <h1 className="text-lg font-semibold">Accounts</h1>
      {state === null ? <p className="text-sm text-muted-foreground">Loading accounts…</p> : null}
      {state && 'error' in state ? (
        <p className="text-sm text-destructive">{state.error}</p>
      ) : null}
      {startError ? <p className="text-sm text-destructive">{startError}</p> : null}
      {state && 'connections' in state
        ? state.connections.map((connection) => (
            <Card key={connection.bank}>
              <CardHeader>
                <CardTitle>{connection.bank}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                {connection.connected ? (
                  <>
                    {connection.validUntil ? (
                      <p className="text-sm text-muted-foreground">
                        Valid until{' '}
                        {formatTimestamp(connection.validUntil) ?? connection.validUntil}
                      </p>
                    ) : null}
                    <ul className="flex flex-col gap-1 text-sm">
                      {connection.accounts.map((account) => (
                        <li key={account.id}>
                          {[account.name, account.ibanMasked, account.currency]
                            .filter(Boolean)
                            .join(' · ')}
                        </li>
                      ))}
                    </ul>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">Not connected.</p>
                )}
                <div>
                  <Button
                    variant={connection.connected ? 'outline' : 'default'}
                    disabled={starting !== null}
                    onClick={() => void start(connection.bank)}
                  >
                    {starting === connection.bank
                      ? 'Redirecting…'
                      : connection.connected
                        ? 'Reconnect'
                        : 'Connect'}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))
        : null}
    </div>
  )
}
