import { LoaderCircle } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { AgentIcon } from '@/components/AgentIcon'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Button } from '@/components/ui/button'
import { AGENTS, type AgentInfo } from '@/lib/agents'
import { api, type AgentName } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { describeApiError } from '@/lib/http'
import { useMe } from '@/lib/me'

// The everyday assistants first; Document Copilot is the original demo.
const PICKER_ORDER: AgentName[] = ['finance', 'email', 'documents']

function AgentCard({
  agent,
  opening,
  disabled,
  onOpen,
}: {
  agent: AgentInfo
  opening: boolean
  disabled: boolean
  onOpen: () => void
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onOpen}
      className="flex h-full flex-col gap-4 rounded-xl border border-border bg-card p-5 text-left shadow-sm transition-[transform,box-shadow,border-color] duration-150 outline-none hover:-translate-y-0.5 hover:border-ring/50 hover:shadow-md focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-wait disabled:opacity-60 disabled:hover:translate-y-0 motion-reduce:transition-none motion-reduce:hover:translate-y-0"
    >
      <span className="flex items-start justify-between">
        <AgentIcon agent={agent} className="size-11 rounded-lg" />
        {opening ? (
          <LoaderCircle className="size-4 animate-spin text-muted-foreground" aria-label="Opening" />
        ) : null}
      </span>
      <span className="flex flex-1 flex-col gap-1">
        <span className="font-heading text-base font-semibold">{agent.title}</span>
        <span className="text-sm text-muted-foreground">{agent.description}</span>
      </span>
    </button>
  )
}

export function AgentPickerPage() {
  const { email, agents } = useMe()
  const { signOut } = useAuth()
  const navigate = useNavigate()
  const [opening, setOpening] = useState<AgentName | null>(null)
  const [error, setError] = useState<string | null>(null)
  const available = PICKER_ORDER.filter((name) => agents.includes(name)).map((name) => AGENTS[name])

  async function open(agent: AgentInfo) {
    if (!agent.hasThreads) {
      void navigate(agent.path)
      return
    }
    setOpening(agent.name)
    setError(null)
    try {
      const thread = await api.createThread(agent.name)
      void navigate(`${agent.path}/${thread.id}`)
    } catch (caught: unknown) {
      setError(describeApiError(caught))
      setOpening(null)
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-end gap-4 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-2">
          <span className="hidden text-sm text-muted-foreground sm:inline">{email}</span>
          <Button
            variant="outline"
            onClick={() => {
              void signOut()
            }}
          >
            Sign out
          </Button>
          <ThemeToggle />
        </div>
      </header>
      <main className="flex flex-1 flex-col items-center justify-center gap-8 px-4 pt-6 pb-16 sm:px-6">
        <div className="flex max-w-xl flex-col items-center gap-2 text-center">
          <h1 className="font-heading text-2xl font-semibold tracking-tight sm:text-3xl">
            Welcome to Borbfolio
          </h1>
          <p className="text-sm text-muted-foreground sm:text-base">
            Which assistant do you want to work with?
          </p>
        </div>
        <div
          className={
            available.length >= 3
              ? 'grid w-full max-w-4xl gap-4 sm:grid-cols-2 lg:grid-cols-3'
              : 'grid w-full max-w-2xl gap-4 sm:grid-cols-2'
          }
        >
          {available.map((agent) => (
            <AgentCard
              key={agent.name}
              agent={agent}
              opening={opening === agent.name}
              disabled={opening !== null}
              onOpen={() => {
                void open(agent)
              }}
            />
          ))}
        </div>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
      </main>
    </div>
  )
}
