import { useEffect, useState } from 'react'

import { api, type Transaction } from '@/lib/api'
import { formatIsoDay } from '@/lib/format'
import { describeApiError } from '@/lib/http'

type State = { transactions: Transaction[] } | { error: string } | null

function formatAmount(transaction: Transaction): string {
  const amount = Number(transaction.amount)
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: transaction.currency,
    }).format(amount)
  } catch {
    // Unknown currency codes throw; show the raw value rather than nothing.
    return `${transaction.amount} ${transaction.currency}`
  }
}

export function TransactionsPage() {
  const [state, setState] = useState<State>(null)

  useEffect(() => {
    let cancelled = false
    api
      .listTransactions()
      .then((transactions) => {
        if (!cancelled) {
          setState({ transactions })
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

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
      <h1 className="text-lg font-semibold">Transactions</h1>
      {state === null ? (
        <p className="text-sm text-muted-foreground">Loading transactions…</p>
      ) : null}
      {state && 'error' in state ? (
        <p className="text-sm text-destructive">{state.error}</p>
      ) : null}
      {state && 'transactions' in state && state.transactions.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No transactions yet. Sync your accounts from the Accounts page.
        </p>
      ) : null}
      {state && 'transactions' in state && state.transactions.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground">
              <tr className="border-b">
                <th className="py-2 pr-4 font-medium">Date</th>
                <th className="py-2 pr-4 font-medium">Account</th>
                <th className="py-2 pr-4 font-medium">Counterparty</th>
                <th className="py-2 text-right font-medium">Amount</th>
              </tr>
            </thead>
            <tbody>
              {state.transactions.map((transaction) => (
                <tr key={transaction.id} className="border-b last:border-0">
                  <td className="whitespace-nowrap py-2 pr-4">
                    {formatIsoDay(transaction.date) ?? transaction.date}
                  </td>
                  <td className="whitespace-nowrap py-2 pr-4">
                    {[transaction.bank, transaction.accountName].filter(Boolean).join(' · ')}
                  </td>
                  <td className="py-2 pr-4">{transaction.counterparty ?? '—'}</td>
                  <td
                    className={`whitespace-nowrap py-2 text-right tabular-nums ${
                      transaction.amount.startsWith('-') ? 'text-destructive/80' : ''
                    }`}
                  >
                    {formatAmount(transaction)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}
