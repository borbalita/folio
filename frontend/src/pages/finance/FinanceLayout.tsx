import { ChevronLeft } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'

import { AgentIcon } from '@/components/AgentIcon'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Button } from '@/components/ui/button'
import { AGENTS } from '@/lib/agents'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { expiryMessage } from '@/lib/reconnect'

const SECTIONS = [
  { to: '/finance/invoices', label: 'Invoices' },
  { to: '/finance/transactions', label: 'Transactions' },
  { to: '/finance/accounts', label: 'Accounts' },
]

export function FinanceLayout() {
  const { user, signOut } = useAuth()
  const { pathname } = useLocation()
  const [warnings, setWarnings] = useState<string[]>([])

  // Re-read on navigation, so a reconnect clears the warning without a reload.
  useEffect(() => {
    let cancelled = false
    api
      .listBankConnections()
      .then((connections) => {
        if (!cancelled) {
          setWarnings(connections.flatMap((c) => expiryMessage(c) ?? []))
        }
      })
      .catch(() => {
        // The warning is a convenience; the Accounts page shows the real error.
      })
    return () => {
      cancelled = true
    }
  }, [pathname])

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="flex w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
        <div className="border-b border-sidebar-border p-3">
          <Link
            to="/"
            aria-label={`${AGENTS.finance.title}. Back to all assistants`}
            className="group flex items-center gap-2 rounded-md p-1 outline-none hover:bg-sidebar-accent/60 focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <AgentIcon agent={AGENTS.finance} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold">{AGENTS.finance.title}</p>
              <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
            </div>
            <ChevronLeft className="size-4 text-muted-foreground group-hover:text-foreground" />
          </Link>
        </div>
        <nav className="flex min-h-0 flex-1 flex-col gap-0.5 p-2">
          {SECTIONS.map((section) => (
            <NavLink
              key={section.to}
              to={section.to}
              className={({ isActive }) =>
                [
                  'rounded-md px-2 py-1.5 text-sm',
                  isActive
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                    : 'hover:bg-sidebar-accent/60',
                ].join(' ')
              }
            >
              {section.label}
            </NavLink>
          ))}
        </nav>
        <div className="flex gap-2 border-t border-sidebar-border p-3">
          <Button
            variant="outline"
            className="flex-1"
            onClick={() => {
              void signOut()
            }}
          >
            Sign out
          </Button>
          <ThemeToggle />
        </div>
      </aside>
      <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-auto p-6">
        {warnings.length > 0 ? (
          <div
            role="status"
            className="mx-auto mb-4 flex w-full max-w-4xl flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm"
          >
            <span>{warnings.join(' ')}</span>
            <Link to="/finance/accounts" className="underline">
              Reconnect on Accounts
            </Link>
          </div>
        ) : null}
        <Outlet />
      </main>
    </div>
  )
}
