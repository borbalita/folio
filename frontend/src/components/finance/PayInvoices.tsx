import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { describeApiError } from '@/lib/http'

interface Props {
  /** Open invoices to pay; empty disables the button. */
  invoiceIds: string[]
  label: string
  /** For example while the invoice has unsaved edits. */
  disabled?: boolean
}

/** Prepare the payments and open them one by one. The banking app that scans the QR pays. */
export function PayInvoices({ invoiceIds, label, disabled = false }: Props) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function prepare() {
    setBusy(true)
    setError(null)
    try {
      const result = await api.createPaymentDrafts(invoiceIds)
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

  // A fragment, so the button sits in the parent's button row.
  return (
    <>
      <Button
        type="button"
        size="sm"
        disabled={disabled || busy || invoiceIds.length === 0}
        onClick={() => void prepare()}
      >
        {label}
      </Button>
      {error ? <span className="text-sm text-destructive">{error}</span> : null}
    </>
  )
}
