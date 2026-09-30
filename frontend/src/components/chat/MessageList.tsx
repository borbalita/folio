import { useEffect, useRef } from 'react'

import { ScrollArea } from '@/components/ui/scroll-area'
import { AssistantMarkdown } from '@/components/chat/AssistantMarkdown'
import { ChatIcon } from '@/components/chat/ChatIcon'
import { PendingReply, ReplyError } from '@/components/chat/ChatStatus'
import { CitationChips } from '@/components/chat/CitationChips'
import { citationsOf, textOf, type CopilotUIMessage } from '@/lib/chat-messages'

export type SelectedCitation = {
  messageId: string
  citationIndex: number
}

interface MessageListProps {
  messages: CopilotUIMessage[]
  selected: SelectedCitation | null
  pendingLabel: string | null
  error: string | null
  onSelect: (messageId: string, citationIndex: number) => void
  onRetry: () => void
}

export function MessageList({
  messages,
  selected,
  pendingLabel,
  error,
  onSelect,
  onRetry,
}: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null)
  const lastText = messages.length > 0 ? textOf(messages[messages.length - 1]) : ''

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages.length, lastText, pendingLabel, error])

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center p-8">
        <p className="text-sm text-muted-foreground">Send a message to start this chat.</p>
      </div>
    )
  }

  return (
    <ScrollArea className="min-h-0 flex-1">
      <div className="mx-auto flex max-w-2xl flex-col gap-4 p-4">
        {messages.map((message) => {
          const isUser = message.role === 'user'
          const body = textOf(message)
          const citations = citationsOf(message)
          if (!isUser && body.length === 0) {
            return null
          }
          return (
            <div
              key={message.id}
              className={isUser ? 'flex justify-end' : 'flex items-start justify-start gap-2'}
            >
              {isUser ? null : <ChatIcon className="size-7" />}
              <div
                className={
                  isUser
                    ? 'max-w-[80%] rounded-lg bg-user-message px-3 py-2 text-sm text-user-message-foreground'
                    : 'max-w-[80%] overflow-x-auto rounded-lg bg-assistant px-3 py-2 text-sm text-assistant-foreground'
                }
              >
                {isUser ? (
                  <p className="whitespace-pre-wrap">{body}</p>
                ) : (
                  <>
                    <AssistantMarkdown
                      citationIndexes={citations.map((citation) => citation.citationIndex)}
                      selectedIndex={
                        selected?.messageId === message.id ? selected.citationIndex : null
                      }
                      onSelect={(citationIndex) => {
                        onSelect(message.id, citationIndex)
                      }}
                    >
                      {body}
                    </AssistantMarkdown>
                    <CitationChips
                      citations={citations}
                      selectedIndex={
                        selected?.messageId === message.id ? selected.citationIndex : null
                      }
                      onSelect={(citationIndex) => {
                        onSelect(message.id, citationIndex)
                      }}
                    />
                  </>
                )}
              </div>
            </div>
          )
        })}
        {pendingLabel ? <PendingReply label={pendingLabel} /> : null}
        {error ? <ReplyError message={error} onRetry={onRetry} /> : null}
        <div ref={endRef} />
      </div>
    </ScrollArea>
  )
}
