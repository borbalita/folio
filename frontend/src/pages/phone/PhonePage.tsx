import { ChevronLeft, LoaderCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { AgentIcon } from '@/components/AgentIcon'
import { ThemeToggle } from '@/components/ThemeToggle'
import { AGENTS } from '@/lib/agents'
import { api, type PhonePersona } from '@/lib/api'
import { describeApiError } from '@/lib/http'
import { CallScreen } from '@/pages/phone/CallScreen'

function PersonaCard({ persona, onCall }: { persona: PhonePersona; onCall: () => void }) {
  return (
    <button
      type="button"
      disabled={!persona.available}
      onClick={onCall}
      className="flex flex-col gap-1 rounded-xl border border-border bg-card p-5 text-left shadow-sm transition-[transform,box-shadow,border-color] duration-150 outline-none hover:-translate-y-0.5 hover:border-ring/50 hover:shadow-md focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0 disabled:hover:shadow-sm motion-reduce:transition-none motion-reduce:hover:translate-y-0"
    >
      <span className="flex items-center justify-between gap-2">
        <span className="font-heading text-base font-semibold">{persona.name}</span>
        {persona.available ? null : (
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
            Coming soon
          </span>
        )}
      </span>
      <span className="text-sm text-muted-foreground">{persona.description}</span>
    </button>
  )
}

export function PhonePage() {
  const [personas, setPersonas] = useState<PhonePersona[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [calling, setCalling] = useState<PhonePersona | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .listPhonePersonas()
      .then((list) => {
        if (!cancelled) {
          setPersonas(list)
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

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <Link
          to="/"
          aria-label={`${AGENTS.phone.title}. Back to all assistants`}
          className="group flex items-center gap-2 rounded-md p-1 outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <ChevronLeft className="size-4 text-muted-foreground group-hover:text-foreground" />
          <AgentIcon agent={AGENTS.phone} />
          <span className="text-sm font-semibold">{AGENTS.phone.title}</span>
        </Link>
        <ThemeToggle />
      </header>
      <main className="flex flex-1 flex-col items-center px-4 pt-6 pb-16 sm:px-6">
        {calling ? (
          <CallScreen
            persona={calling}
            onClose={() => {
              setCalling(null)
            }}
          />
        ) : (
          <div className="flex w-full max-w-3xl flex-col items-center gap-8">
            <div className="flex flex-col items-center gap-2 text-center">
              <h1 className="font-heading text-2xl font-semibold tracking-tight sm:text-3xl">
                {AGENTS.phone.emptyTitle}
              </h1>
              <p className="text-sm text-muted-foreground sm:text-base">
                Pick a persona and they'll ring you. You talk out loud, so have your mic and
                speakers ready.
              </p>
            </div>
            {personas ? (
              <div className="grid w-full gap-4 sm:grid-cols-3">
                {personas.map((persona) => (
                  <PersonaCard
                    key={persona.id}
                    persona={persona}
                    onCall={() => {
                      setCalling(persona)
                    }}
                  />
                ))}
              </div>
            ) : error ? null : (
              <LoaderCircle className="size-5 animate-spin text-muted-foreground" aria-label="Loading" />
            )}
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
          </div>
        )}
      </main>
    </div>
  )
}
