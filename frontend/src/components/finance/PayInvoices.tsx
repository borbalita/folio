import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { api, type BankAccount, type BankName } from '@/lib/api'
import { describeApiError } from '@/lib/http'

interface Props {
  /** Open invoices to pay; empty disables the button. */
  invoiceIds: string[]
  label: string
  /** Selected invoices that are not open, mentioned as skipped. */
  skipped?: number
  /** For example while the invoice has unsaved edits. */
  disabled?: boolean
}

/** Pick the account to pay from, prepare the payments, and open them one by one. */
export function PayInvoices({ invoiceIds, label, skipped = 0, disabled = false }: Props) {
  const navigate = useNavigate()
  const [accounts, setAccounts] = useState<{ bank: BankName; account: BankAccount }[] | null>(
    null,
  )
  const [accountId, setAccountId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function choose() {
    setError(null)
    try {
      const connections = await api.listBankConnections()
      // Only accounts with an IBAN can send a SEPA transfer; PayPal has none.
      const payable = connections
        .filter((connection) => connection.connected)
        .flatMap((connection) =>
          connection.accounts
            .filter((account) => account.ibanMasked)
            .map((account) => ({ bank: connection.bank, account })),
        )
      if (payable.length === 0) {
        setError('Connect a bank account with an IBAN on the Accounts page first.')
        return
      }
      setAccounts(payable)
      setAccountId(payable[0].account.id)
    } catch (caught: unknown) {
      setError(describeApiError(caught))
    }
  }

  async function prepare() {
    setBusy(true)
    setError(null)
    try {
      const result = await api.createPaymentDrafts(invoiceIds, accountId)
      if (result.drafts.length === 0) {
        setError('None of these invoices is open, so there is nothing to pay.')
        return
      }
      navigate(`/finance/payments?drafts=${result.drafts.map((draft) => draft.id).join(',')}`)
    } catch (caught: unknown) {
      setError(describeApiError(caught))
    } finally {
      setBusy(false)
    }
  }

  // A fragment, so the button sits in the parent's button row and the picker wraps below it.
  return (
    <>
      <Button
        type="button"
        size="sm"
        disabled={disabled || busy || invoiceIds.length === 0}
        onClick={() => void choose()}
      >
        {label}
      </Button>
      {error ? <span className="text-sm text-destructive">{error}</span> : null}
      {accounts && invoiceIds.length > 0 && !disabled ? (
        <div className="order-last flex basis-full flex-wrap items-center gap-2 rounded-md border border-border p-3 text-sm">
          <label htmlFor="pay-from">
            Pay {invoiceIds.length === 1 ? 'from' : `${invoiceIds.length} from`}
          </label>
          <select
            id="pay-from"
            className="rounded-md border border-border bg-background px-2 py-1"
            value={accountId}
            onChange={(event) => setAccountId(event.target.value)}
          >
            {accounts.map(({ bank, account }) => (
              <option key={account.id} value={account.id}>
                {bank}
                {account.name ? ` · ${account.name}` : ''} · {account.ibanMasked}
              </option>
            ))}
          </select>
          <Button
            type="button"
            size="sm"
            disabled={busy || !accountId}
            onClick={() => void prepare()}
          >
            {invoiceIds.length === 1 ? 'Prepare payment' : 'Prepare payments'}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setAccounts(null)}>
            Close
          </Button>
          {skipped > 0 ? (
            <span className="text-xs text-muted-foreground">
              {skipped} selected invoice{skipped === 1 ? ' is' : 's are'} not open and will be
              skipped.
            </span>
          ) : null}
        </div>
      ) : null}
    </>
  )
}
