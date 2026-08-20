import { useChat } from '@ai-sdk/react'
import { DefaultChatTransport, type UIMessage } from 'ai'
import { useMemo } from 'react'

import { ChatInput } from '@/components/chat/ChatInput'
import { ChatStatus } from '@/components/chat/ChatStatus'
import { MessageList } from '@/components/chat/MessageList'
import { env } from '@/lib/env'
import { getAccessToken } from '@/lib/supabase'

interface ChatThreadViewProps {
  threadId: string
  initialMessages: UIMessage[]
  onTurnFinished: () => void
}

export function ChatThreadView({
  threadId,
  initialMessages,
  onTurnFinished,
}: ChatThreadViewProps) {
  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: `${env.apiBaseUrl}/chat/stream`,
        headers: async (): Promise<Record<string, string>> => {
          const token = await getAccessToken()
          if (!token) {
            return {}
          }
          return { Authorization: `Bearer ${token}` }
        },
        prepareSendMessagesRequest: ({ messages }) => ({
          body: { threadId, messages },
        }),
      }),
    [threadId],
  )

  const { messages, sendMessage, status, error } = useChat({
    id: threadId,
    messages: initialMessages,
    transport,
    onFinish: ({ isError }) => {
      if (!isError) {
        onTurnFinished()
      }
    },
  })

  const busy = status === 'submitted' || status === 'streaming'

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <MessageList messages={messages} />
      <ChatStatus status={status} error={error} />
      <ChatInput
        disabled={busy}
        onSend={(text) => {
          void sendMessage({ text })
        }}
      />
    </div>
  )
}
