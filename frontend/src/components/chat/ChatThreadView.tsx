import { useChat } from '@ai-sdk/react'
import { DefaultChatTransport } from 'ai'
import { useEffect, useMemo, useState } from 'react'

import { ChatInput } from '@/components/chat/ChatInput'
import { MessageList, type SelectedCitation } from '@/components/chat/MessageList'
import { SourcePanel } from '@/components/chat/SourcePanel'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { citationsOf, textOf, type CopilotUIMessage } from '@/lib/chat-messages'
import { env } from '@/lib/env'
import { describeApiError } from '@/lib/http'
import { cn } from '@/lib/utils'
import { getAccessToken } from '@/lib/supabase'

interface ChatThreadViewProps {
  threadId: string
  initialMessages: CopilotUIMessage[]
  placeholder: string
  onTurnFinished: () => void
}

function useIsDesktop() {
  const [isDesktop, setIsDesktop] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(min-width: 768px)').matches,
  )

  useEffect(() => {
    const media = window.matchMedia('(min-width: 768px)')
    function onChange() {
      setIsDesktop(media.matches)
    }
    onChange()
    media.addEventListener('change', onChange)
    return () => {
      media.removeEventListener('change', onChange)
    }
  }, [])

  return isDesktop
}

function citationForSelection(
  messages: CopilotUIMessage[],
  selected: SelectedCitation | null,
) {
  if (selected === null) {
    return null
  }
  const message = messages.find((item) => item.id === selected.messageId)
  if (!message) {
    return null
  }
  return (
    citationsOf(message).find((citation) => citation.citationIndex === selected.citationIndex) ??
    null
  )
}

export function ChatThreadView({
  threadId,
  initialMessages,
  placeholder,
  onTurnFinished,
}: ChatThreadViewProps) {
  const isDesktop = useIsDesktop()
  const [selected, setSelected] = useState<SelectedCitation | null>(null)
  const [stage, setStage] = useState<string | null>(null)

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

  const { messages, sendMessage, regenerate, status, error } = useChat<CopilotUIMessage>({
    id: threadId,
    messages: initialMessages,
    transport,
    onData: (part) => {
      if (part.type === 'data-status') {
        setStage(part.data.label)
      }
    },
    onFinish: ({ isError }) => {
      setStage(null)
      if (!isError) {
        onTurnFinished()
      }
    },
    onError: () => {
      setStage(null)
    },
  })

  const busy = status === 'submitted' || status === 'streaming'
  const lastMessage = messages.at(-1)
  const hasAssistantText =
    lastMessage?.role === 'assistant' && textOf(lastMessage).length > 0
  const failed = status === 'error' || error !== undefined
  const waiting = status === 'submitted' || (status === 'streaming' && !hasAssistantText)
  const pendingLabel = !failed && waiting ? (stage ?? 'Thinking') : null
  const errorMessage = failed
    ? describeApiError(error ?? new Error('The chat request failed.'))
    : null
  const citation = citationForSelection(messages, selected)
  const panelOpen = citation !== null
  const [shownCitation, setShownCitation] = useState(citation)
  if (citation !== null && citation !== shownCitation) {
    setShownCitation(citation)
  }

  useEffect(() => {
    if (!panelOpen) {
      return
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setSelected(null)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [panelOpen])

  function onSelect(messageId: string, citationIndex: number) {
    setSelected((current) =>
      current?.messageId === messageId && current.citationIndex === citationIndex
        ? null
        : { messageId, citationIndex },
    )
  }

  function onClose() {
    setSelected(null)
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <MessageList
          messages={messages}
          selected={selected}
          pendingLabel={pendingLabel}
          error={errorMessage}
          onSelect={onSelect}
          onRetry={() => {
            void regenerate()
          }}
        />
        <ChatInput
          disabled={busy}
          placeholder={placeholder}
          onSend={(text) => {
            void sendMessage({ text })
          }}
        />
      </div>
      <aside
        inert={!panelOpen}
        className={cn(
          'hidden shrink-0 overflow-hidden transition-[width] duration-200 ease-out motion-reduce:transition-none md:block',
          panelOpen ? 'w-80 border-l' : 'w-0',
        )}
      >
        <div className="flex h-full w-80 flex-col">
          {shownCitation ? <SourcePanel citation={shownCitation} onClose={onClose} /> : null}
        </div>
      </aside>
      <Sheet
        open={!isDesktop && selected !== null}
        onOpenChange={(open) => {
          if (!open) {
            onClose()
          }
        }}
      >
        <SheetContent
          side="right"
          showCloseButton={false}
          className="w-80 p-0 motion-reduce:transition-none motion-reduce:data-ending-style:translate-x-0 motion-reduce:data-starting-style:translate-x-0"
        >
          <SheetHeader className="sr-only">
            <SheetTitle>Cited source</SheetTitle>
            <SheetDescription>Source cited by the assistant.</SheetDescription>
          </SheetHeader>
          {shownCitation ? <SourcePanel citation={shownCitation} onClose={onClose} /> : null}
        </SheetContent>
      </Sheet>
    </div>
  )
}
