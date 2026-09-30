import { RotateCcw } from 'lucide-react'

import { ChatIcon } from '@/components/chat/ChatIcon'
import { Button } from '@/components/ui/button'

export function PendingReply({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2" role="status">
      <ChatIcon className="size-7" />
      <p className="shimmer-text text-sm">{label}…</p>
    </div>
  )
}

export function ReplyError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex items-start gap-2" role="alert">
      <ChatIcon className="size-7" />
      <div className="flex flex-col items-start gap-2 pt-1">
        <p className="text-sm text-destructive">{message}</p>
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RotateCcw />
          Retry
        </Button>
      </div>
    </div>
  )
}
