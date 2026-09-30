import { Link, NavLink } from 'react-router-dom'
import { ChevronLeft, Plus } from 'lucide-react'

import { ChatIcon } from '@/components/chat/ChatIcon'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { AgentInfo } from '@/lib/agents'
import type { Thread } from '@/lib/api'

interface ThreadSidebarProps {
  agent: AgentInfo
  threads: Thread[]
  loading: boolean
  error: string | null
  creating: boolean
  userEmail: string | undefined
  onNewChat: () => void
  onSignOut: () => void
}

export function ThreadSidebar({
  agent,
  threads,
  loading,
  error,
  creating,
  userEmail,
  onNewChat,
  onSignOut,
}: ThreadSidebarProps) {
  return (
    <aside className="flex w-64 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground">
      <div className="flex flex-col gap-2 border-b p-3">
        <Link
          to="/"
          aria-label={`${agent.title}. Back to all assistants`}
          className="group flex items-center gap-2 rounded-md p-1 outline-none hover:bg-sidebar-accent/60 focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <ChatIcon className="size-8" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold">{agent.title}</p>
            <p className="truncate text-xs text-muted-foreground">{userEmail}</p>
          </div>
          <ChevronLeft className="size-4 text-muted-foreground group-hover:text-foreground" />
        </Link>
        <Button onClick={onNewChat} disabled={creating} className="w-full">
          <Plus />
          New chat
        </Button>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <nav className="flex flex-col gap-0.5 p-2">
          {loading ? (
            <p className="px-2 py-3 text-sm text-muted-foreground">Loading threads…</p>
          ) : null}
          {error ? <p className="px-2 py-3 text-sm text-destructive">{error}</p> : null}
          {!loading && !error && threads.length === 0 ? (
            <p className="px-2 py-3 text-sm text-muted-foreground">No threads yet.</p>
          ) : null}
          {threads.map((thread) => (
            <NavLink
              key={thread.id}
              to={`${agent.path}/${thread.id}`}
              className={({ isActive }) =>
                [
                  'truncate rounded-md px-2 py-1.5 text-sm',
                  isActive
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                    : 'hover:bg-sidebar-accent/60',
                ].join(' ')
              }
            >
              {thread.title}
            </NavLink>
          ))}
        </nav>
      </ScrollArea>

      <div className="border-t p-3">
        <Button variant="outline" className="w-full" onClick={onSignOut}>
          Sign out
        </Button>
      </div>
    </aside>
  )
}
