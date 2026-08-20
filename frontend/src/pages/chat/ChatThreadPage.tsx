import { useEffect, useState } from 'react'
import { Link, useOutletContext, useParams } from 'react-router-dom'
import type { UIMessage } from 'ai'

import { ChatThreadView } from '@/components/chat/ChatThreadView'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { toUIMessages } from '@/lib/chat-messages'
import { describeApiError } from '@/lib/http'

import type { ChatOutletContext } from './ChatPage'

export function ChatThreadPage() {
  const { threadId } = useParams<{ threadId: string }>()
  const { refreshThreads } = useOutletContext<ChatOutletContext>()
  const [loaded, setLoaded] = useState<{
    threadId: string
    messages: UIMessage[]
  } | null>(null)
  const [error, setError] = useState<{ threadId: string; message: string } | null>(null)

  useEffect(() => {
    if (!threadId) {
      return
    }

    let cancelled = false
    api
      .getMessages(threadId)
      .then((rows) => {
        if (!cancelled) {
          setLoaded({ threadId, messages: toUIMessages(rows) })
          setError(null)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setLoaded(null)
          setError({ threadId, message: describeApiError(caught) })
        }
      })

    return () => {
      cancelled = true
    }
  }, [threadId])

  if (!threadId) {
    return null
  }

  if (error?.threadId === threadId) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
        <p className="text-sm text-destructive">{error.message}</p>
        <Button render={<Link to="/chat" />}>Back to chats</Button>
      </div>
    )
  }

  if (loaded?.threadId !== threadId) {
    return (
      <div className="flex flex-1 items-center justify-center p-8 text-sm text-muted-foreground">
        Loading messages…
      </div>
    )
  }

  return (
    <ChatThreadView
      key={threadId}
      threadId={threadId}
      initialMessages={loaded.messages}
      onTurnFinished={() => {
        void refreshThreads()
      }}
    />
  )
}
