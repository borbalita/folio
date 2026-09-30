import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'

import { api, type Me } from '@/lib/api'
import { describeApiError } from '@/lib/http'
import { MeContext } from '@/lib/me'

/** Loads `/me` once for the signed-in routes, then renders them with it in context. */
export function MeGate() {
  const [me, setMe] = useState<Me | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .getMe()
      .then((next) => {
        if (!cancelled) {
          setMe(next)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(describeApiError(caught))
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (error) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8 text-sm text-destructive">
        {error}
      </main>
    )
  }

  if (!me) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8 text-muted-foreground">
        Loading…
      </main>
    )
  }

  return (
    <MeContext.Provider value={me}>
      <Outlet />
    </MeContext.Provider>
  )
}
