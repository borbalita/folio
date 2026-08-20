import { describeApiError } from '@/lib/http'

interface ChatStatusProps {
  status: 'submitted' | 'streaming' | 'ready' | 'error'
  error: Error | undefined
}

export function ChatStatus({ status, error }: ChatStatusProps) {
  if (status === 'submitted') {
    return <p className="px-4 pb-2 text-center text-xs text-muted-foreground">Sending…</p>
  }
  if (status === 'streaming') {
    return <p className="px-4 pb-2 text-center text-xs text-muted-foreground">Streaming…</p>
  }
  if (status === 'error' || error) {
    return (
      <p className="px-4 pb-2 text-center text-xs text-destructive">
        {describeApiError(error ?? new Error('The chat request failed.'))}
      </p>
    )
  }
  return null
}
