import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ChatIcon } from '@/components/chat/ChatIcon'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { AGENTS, type AgentInfo } from '@/lib/agents'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { describeApiError } from '@/lib/http'
import { useMe } from '@/lib/me'

export function AgentPickerPage() {
  const { email, agents } = useMe()
  const { signOut } = useAuth()
  const navigate = useNavigate()
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const available = Object.values(AGENTS).filter((agent) => agents.includes(agent.name))

  async function startChat(agent: AgentInfo) {
    if (!agent.hasThreads) {
      void navigate(agent.path)
      return
    }
    setStarting(true)
    try {
      const thread = await api.createThread(agent.name)
      void navigate(`${agent.path}/${thread.id}`)
    } catch (caught: unknown) {
      setError(describeApiError(caught))
      setStarting(false)
    }
  }

  return (
    <main className="relative flex min-h-screen flex-col items-center justify-center gap-8 p-8">
      <div className="absolute top-4 right-4 flex gap-2">
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
      <div className="flex flex-col items-center gap-2 text-center">
        <ChatIcon className="size-10" />
        <h1 className="text-xl font-semibold">Choose an assistant</h1>
        <p className="text-sm text-muted-foreground">{email}</p>
      </div>
      <div className="grid w-full max-w-2xl gap-4 sm:grid-cols-2">
        {available.map((agent) => (
          <button
            key={agent.name}
            type="button"
            disabled={starting}
            onClick={() => {
              void startChat(agent)
            }}
            className="rounded-xl text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-wait disabled:opacity-60"
          >
            <Card className="h-full transition-colors hover:bg-muted/50">
              <CardHeader>
                <CardTitle>{agent.title}</CardTitle>
                <CardDescription>{agent.description}</CardDescription>
              </CardHeader>
            </Card>
          </button>
        ))}
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </main>
  )
}
