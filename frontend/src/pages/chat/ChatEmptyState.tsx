import { useOutletContext } from 'react-router-dom'

import type { ChatOutletContext } from './ChatPage'

export function ChatEmptyState() {
  const { agent } = useOutletContext<ChatOutletContext>()
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center">
      <h1 className="text-lg font-medium">{agent.emptyTitle}</h1>
      <p className="max-w-sm text-sm text-muted-foreground">{agent.emptyHint}</p>
    </div>
  )
}
