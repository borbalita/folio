import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { api } from '@/lib/api'
import { describeApiErrorDetail } from '@/lib/http'

export function BankCallbackPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const started = useRef(false)
  const [apiError, setApiError] = useState<string | null>(null)

  const bankError = params.get('error_description') ?? params.get('error')
  const code = params.get('code')
  const state = params.get('state')

  useEffect(() => {
    // The code is single-use: guard against the StrictMode double effect.
    if (bankError || !code || !state || started.current) {
      return
    }
    started.current = true
    api
      .completeBankConnection(code, state)
      .then(() => navigate('/finance/accounts', { replace: true }))
      .catch((caught: unknown) => setApiError(describeApiErrorDetail(caught)))
  }, [bankError, code, state, navigate])

  const error = bankError ?? apiError ?? (!code || !state ? 'Missing bank response.' : null)

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
      <h1 className="text-lg font-semibold">Bank connection</h1>
      {error ? (
        <>
          <p className="text-sm text-destructive">{error}</p>
          <Link to="/finance/accounts" className="text-sm underline">
            Back to Accounts
          </Link>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">Finishing bank connection…</p>
      )}
    </div>
  )
}
