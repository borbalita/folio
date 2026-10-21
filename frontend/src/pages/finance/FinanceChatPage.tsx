import { useCallback, useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { AGENTS } from '@/lib/agents'
import { api, type Thread } from '@/lib/api'
import { describeApiError } from '@/lib/http'
import type { ChatOutletContext } from '@/pages/chat/ChatPage'

// ChatThreadPage links back to `agent.path`; in Finance the chats live under /finance/chat.
const FINANCE_CHAT = { ...AGENTS.finance, path: '/finance/chat' }

export function FinanceChatPage() {
  const navigate = useNavigate()
  const [threads, setThreads] = useState<Thread[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const refreshThreads = useCallback(async () => {
    try {
      setThreads(await api.listThreads('finance'))
      setError(null)
    } catch (caught: unknown) {
      setError(describeApiError(caught))
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    api
      .listThreads('finance')
      .then((next) => {
        if (!cancelled) {
          setThreads(next)
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

  async function newChat() {
    setCreating(true)
    try {
      const thread = await api.createThread('finance')
      setThreads((current) => [thread, ...(current ?? []).filter((item) => item.id !== thread.id)])
      void navigate(`/finance/chat/${thread.id}`)
    } catch (caught: unknown) {
      setError(describeApiError(caught))
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex w-56 shrink-0 flex-col gap-2 border-r border-border p-3">
        <Button disabled={creating} onClick={() => void newChat()}>
          New chat
        </Button>
        {error ? <p className="text-xs text-destructive">{error}</p> : null}
        <nav className="flex min-h-0 flex-col gap-0.5 overflow-auto">
          {(threads ?? []).map((thread) => (
            <NavLink
              key={thread.id}
              to={`/finance/chat/${thread.id}`}
              className={({ isActive }) =>
                [
                  'truncate rounded-md px-2 py-1.5 text-sm',
                  isActive ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/60',
                ].join(' ')
              }
            >
              {thread.title}
            </NavLink>
          ))}
        </nav>
      </div>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <Outlet context={{ agent: FINANCE_CHAT, refreshThreads } satisfies ChatOutletContext} />
      </div>
    </div>
  )
}

export function FinanceChatEmpty() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center">
      <p className="text-sm font-medium">Ask about your invoices</p>
      <p className="text-sm text-muted-foreground">
        Try “What do I still need to pay?” or “Pay them all”. Payments wait for your approval.
      </p>
    </div>
  )
}
