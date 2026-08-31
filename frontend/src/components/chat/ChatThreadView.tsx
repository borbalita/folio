import { useChat } from '@ai-sdk/react'
import { DefaultChatTransport } from 'ai'
import { useEffect, useMemo, useState } from 'react'

import { ChatInput } from '@/components/chat/ChatInput'
import { ChatStatus } from '@/components/chat/ChatStatus'
import { MessageList, type SelectedCitation } from '@/components/chat/MessageList'
import { SourcePanel } from '@/components/chat/SourcePanel'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { citationsOf, type CopilotUIMessage } from '@/lib/chat-messages'
import { env } from '@/lib/env'
import { getAccessToken } from '@/lib/supabase'

interface ChatThreadViewProps {
  threadId: string
  initialMessages: CopilotUIMessage[]
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

  const { messages, sendMessage, status, error } = useChat<CopilotUIMessage>({
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
  const citation = citationForSelection(messages, selected)

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
        <MessageList messages={messages} selected={selected} onSelect={onSelect} />
        <ChatStatus status={status} error={error} stage={stage} />
        <ChatInput
          disabled={busy}
          onSend={(text) => {
            void sendMessage({ text })
          }}
        />
      </div>
      <aside className="hidden w-80 shrink-0 border-l md:flex md:flex-col">
        <SourcePanel citation={citation} onClose={onClose} />
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
            <SheetTitle>Filing passage</SheetTitle>
            <SheetDescription>Passage cited by the assistant.</SheetDescription>
          </SheetHeader>
          <SourcePanel citation={citation} onClose={onClose} />
        </SheetContent>
      </Sheet>
    </div>
  )
}
