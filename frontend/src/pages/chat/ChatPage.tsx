import { Menu } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'

import { ThreadSidebar } from '@/components/chat/ThreadSidebar'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { AGENTS, type AgentInfo } from '@/lib/agents'
import { useAuth } from '@/lib/auth'
import { api, type AgentName, type Thread } from '@/lib/api'
import { describeApiError } from '@/lib/http'

export interface ChatOutletContext {
  agent: AgentInfo
  refreshThreads: () => Promise<void>
}

export function ChatPage({ agentName }: { agentName: AgentName }) {
  const agent = AGENTS[agentName]
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  // The page the phone menu was opened on: navigating anywhere else closes it.
  const [menuOpenedOn, setMenuOpenedOn] = useState<string | null>(null)
  const [threads, setThreads] = useState<Thread[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const refreshThreads = useCallback(async () => {
    try {
      const next = await api.listThreads(agentName)
      setThreads(next)
      setError(null)
    } catch (caught: unknown) {
      setError(describeApiError(caught))
    }
  }, [agentName])

  useEffect(() => {
    let cancelled = false
    api
      .listThreads(agentName)
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
  }, [agentName])

  async function onNewChat() {
    setCreating(true)
    try {
      const thread = await api.createThread(agentName)
      setThreads((current) => [thread, ...current.filter((item) => item.id !== thread.id)])
      setError(null)
      void navigate(`${agent.path}/${thread.id}`)
    } catch (caught: unknown) {
      setError(describeApiError(caught))
    } finally {
      setCreating(false)
    }
  }

  const sidebar = (
    <ThreadSidebar
      agent={agent}
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
  )

  return (
    <div className="flex h-screen overflow-hidden">
      <div className="hidden md:flex">{sidebar}</div>
      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-border px-2 py-1.5 md:hidden">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Open chats"
            onClick={() => {
              setMenuOpenedOn(pathname)
            }}
          >
            <Menu className="size-5" />
          </Button>
          <span className="truncate text-sm font-semibold">{agent.title}</span>
        </div>
        <Outlet context={{ agent, refreshThreads } satisfies ChatOutletContext} />
      </main>
      <Sheet
        open={menuOpenedOn === pathname}
        onOpenChange={(open) => {
          if (!open) {
            setMenuOpenedOn(null)
          }
        }}
      >
        <SheetContent side="left" showCloseButton={false} className="w-64 gap-0 p-0 md:hidden">
          <SheetHeader className="sr-only">
            <SheetTitle>Chats</SheetTitle>
          </SheetHeader>
          <div className="flex min-h-0 flex-1">{sidebar}</div>
        </SheetContent>
      </Sheet>
    </div>
  )
}
