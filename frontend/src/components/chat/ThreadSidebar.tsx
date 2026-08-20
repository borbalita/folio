import { NavLink } from 'react-router-dom'
import { Plus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { Thread } from '@/lib/api'

interface ThreadSidebarProps {
  threads: Thread[]
  loading: boolean
  error: string | null
  creating: boolean
  userEmail: string | undefined
  onNewChat: () => void
  onSignOut: () => void
}

export function ThreadSidebar({
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
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">Document Copilot</p>
            <p className="truncate text-xs text-muted-foreground">{userEmail}</p>
          </div>
        </div>
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
              to={`/chat/${thread.id}`}
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
