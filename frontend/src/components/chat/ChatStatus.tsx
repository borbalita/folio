import { describeApiError } from '@/lib/http'

interface ChatStatusProps {
  status: 'submitted' | 'streaming' | 'ready' | 'error'
  error: Error | undefined
  stage: string | null
}

export function ChatStatus({ status, error, stage }: ChatStatusProps) {
  if (status === 'error' || error) {
    return (
      <p className="px-4 pb-2 text-center text-xs text-destructive">
        {describeApiError(error ?? new Error('The chat request failed.'))}
      </p>
    )
  }
  if (status === 'submitted' || status === 'streaming') {
    const label = stage ?? 'Looking through filings'
    return (
      <p className="flex items-center justify-center gap-2 px-4 pb-2 text-xs text-muted-foreground">
        <span className="inline-block size-1.5 animate-pulse rounded-full bg-muted-foreground motion-reduce:animate-none" />
        {label}
      </p>
    )
  }
  return null
}
