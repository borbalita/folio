import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth'
import { env } from '@/lib/env'
import { http } from '@/lib/http'

export function ChatPage() {
  const { user, signOut } = useAuth()
  const [me, setMe] = useState<string | null>(null)
  const [meError, setMeError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    http
      .get<{ id: string; email: string }>('/me')
      .then((data) => {
        if (!cancelled) {
          setMe(`${data.email} (${data.id})`)
          setMeError(null)
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setMe(null)
          setMeError(error instanceof Error ? error.message : 'Failed to call /me')
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 p-8">
      <header className="flex items-center justify-between border-b pb-4">
        <div>
          <h1 className="text-xl font-semibold">Document Copilot</h1>
          <p className="text-sm text-muted-foreground">{user?.email}</p>
        </div>
        <Button variant="outline" onClick={() => void signOut()}>
          Sign out
        </Button>
      </header>

      <section className="flex flex-col gap-2">
        <h2 className="font-medium">Session check</h2>
        <p className="text-sm text-muted-foreground">
          Backend: <code>{env.apiBaseUrl}</code>
        </p>
        {me ? <p className="text-sm">GET /me → {me}</p> : null}
        {meError ? <p className="text-sm text-destructive">{meError}</p> : null}
        {!me && !meError ? (
          <p className="text-sm text-muted-foreground">Calling GET /me…</p>
        ) : null}
      </section>

      <p className="text-sm text-muted-foreground">
        Chat UI arrives in Step 10. This page is the protected landing surface for auth.
      </p>
    </main>
  )
}
