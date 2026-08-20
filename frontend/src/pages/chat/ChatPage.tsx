import { useCallback, useEffect, useState } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'

import { ThreadSidebar } from '@/components/chat/ThreadSidebar'
import { useAuth } from '@/lib/auth'
import { api, type Thread } from '@/lib/api'
import { describeApiError } from '@/lib/http'

export interface ChatOutletContext {
  refreshThreads: () => Promise<void>
}

export function ChatPage() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const [threads, setThreads] = useState<Thread[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const refreshThreads = useCallback(async () => {
    try {
      const next = await api.listThreads()
      setThreads(next)
      setError(null)
    } catch (caught: unknown) {
      setError(describeApiError(caught))
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    api
      .listThreads()
      .then((next) => {
        if (!cancelled) {
          setThreads(next)
          setError(null)
          setLoading(false)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(describeApiError(caught))
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function onNewChat() {
    setCreating(true)
    try {
      const thread = await api.createThread()
      setThreads((current) => [thread, ...current.filter((item) => item.id !== thread.id)])
      setError(null)
      void navigate(`/chat/${thread.id}`)
    } catch (caught: unknown) {
      setError(describeApiError(caught))
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <ThreadSidebar
        threads={threads}
        loading={loading}
        error={error}
        creating={creating}
        userEmail={user?.email}
        onNewChat={() => {
          void onNewChat()
        }}
        onSignOut={() => {
          void signOut()
        }}
      />
      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        <Outlet
          context={{ refreshThreads } satisfies ChatOutletContext}
        />
      </main>
    </div>
  )
}
