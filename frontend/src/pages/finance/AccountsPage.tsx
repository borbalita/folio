import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { api, type BankConnection, type BankName } from '@/lib/api'
import { formatTimestamp } from '@/lib/format'
import { describeApiErrorDetail } from '@/lib/http'
import {
  clearReconnectQueue,
  expiryMessage,
  goToBank,
  needsReconnect,
  reconnectAll,
} from '@/lib/reconnect'

type State = { connections: BankConnection[] } | { error: string } | null

export function AccountsPage() {
  const [state, setState] = useState<State>(null)
  const [starting, setStarting] = useState<BankName | null>(null)
  const [startError, setStartError] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState<{ message: string; failed: boolean } | null>(
    null,
  )

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
          setState({ error: describeApiErrorDetail(caught) })
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
        // Back from a bank page without its callback: Reconnect all was abandoned.
        clearReconnectQueue()
      }
    }
    window.addEventListener('pageshow', onPageShow)
    return () => window.removeEventListener('pageshow', onPageShow)
  }, [])

  async function start(bank: BankName) {
    // A single connect must not pick up banks left queued by an abandoned Reconnect all.
    clearReconnectQueue()
    setStarting(bank)
    setStartError(null)
    try {
      await goToBank(bank)
    } catch (caught: unknown) {
      setStartError(describeApiErrorDetail(caught))
      setStarting(null)
    }
  }

  const toReconnect =
    state && 'connections' in state
      ? state.connections.flatMap((connection) =>
          connection.connectable && needsReconnect(connection) ? [connection.bank] : [],
        )
      : []

  async function startReconnectAll() {
    setStarting(toReconnect[0] ?? null)
    setStartError(null)
    try {
      await reconnectAll(toReconnect)
    } catch (caught: unknown) {
      setStartError(describeApiErrorDetail(caught))
      setStarting(null)
    }
  }

  async function syncNow() {
    setSyncing(true)
    setSyncResult(null)
    try {
      const { added } = await api.syncBanks()
      setSyncResult({
        message: `Added ${added} ${added === 1 ? 'transaction' : 'transactions'}.`,
        failed: false,
      })
    } catch (caught: unknown) {
      setSyncResult({ message: describeApiErrorDetail(caught), failed: true })
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-lg font-semibold">Accounts</h1>
        <div className="flex gap-2">
          {toReconnect.length > 0 ? (
            <Button disabled={starting !== null} onClick={() => void startReconnectAll()}>
              Reconnect all
            </Button>
          ) : null}
          <Button variant="outline" disabled={syncing} onClick={() => void syncNow()}>
            {syncing ? 'Syncing…' : 'Sync now'}
          </Button>
        </div>
      </div>
      {syncResult ? (
        <p
          className={
            syncResult.failed ? 'text-sm text-destructive' : 'text-sm text-muted-foreground'
          }
        >
          {syncResult.message}
        </p>
      ) : null}
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
                    {expiryMessage(connection) ? (
                      <p className="text-sm text-destructive">{expiryMessage(connection)}</p>
                    ) : null}
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
                {/* Demo banks are fixture data; the server refuses to connect them. */}
                {!connection.connectable ? null : (
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
                )}
              </CardContent>
            </Card>
          ))
        : null}
    </div>
  )
}
