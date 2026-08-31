import { ScrollArea } from '@/components/ui/scroll-area'
import { AssistantMarkdown } from '@/components/chat/AssistantMarkdown'
import { CitationChips } from '@/components/chat/CitationChips'
import { citationsOf, textOf, type CopilotUIMessage } from '@/lib/chat-messages'

export type SelectedCitation = {
  messageId: string
  citationIndex: number
}

interface MessageListProps {
  messages: CopilotUIMessage[]
  selected: SelectedCitation | null
  onSelect: (messageId: string, citationIndex: number) => void
}

export function MessageList({ messages, selected, onSelect }: MessageListProps) {
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
          return (
            <div
              key={message.id}
              className={isUser ? 'flex justify-end' : 'flex justify-start'}
            >
              <div
                className={
                  isUser
                    ? 'max-w-[80%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground'
                    : 'max-w-[80%] overflow-x-auto rounded-lg bg-muted px-3 py-2 text-sm'
                }
              >
                {isUser ? (
                  <p className="whitespace-pre-wrap">{body}</p>
                ) : (
                  <>
                    <AssistantMarkdown>{body}</AssistantMarkdown>
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
      </div>
    </ScrollArea>
  )
}
