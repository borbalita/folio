import { useEffect, useState } from 'react'

import { api } from '@/lib/api'
import { describeApiError } from '@/lib/http'

interface Props {
  attachment: { id: string; filename: string }
}

export function PdfViewer({ attachment }: Props) {
  const [state, setState] = useState<{ url: string } | { error: string } | null>(null)

  useEffect(() => {
    let cancelled = false
    let url: string | null = null
    api
      .getAttachment(attachment.id)
      .then((blob) => {
        if (cancelled) {
          return
        }
        url = URL.createObjectURL(blob)
        setState({ url })
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setState({ error: describeApiError(caught) })
        }
      })
    return () => {
      cancelled = true
      if (url) {
        URL.revokeObjectURL(url)
      }
    }
  }, [attachment.id])

  return (
    <figure className="flex flex-col gap-2">
      {state === null ? <p className="text-sm text-muted-foreground">Loading PDF…</p> : null}
      {state && 'error' in state ? <p className="text-sm text-destructive">{state.error}</p> : null}
      {state && 'url' in state ? (
        <iframe
          src={state.url}
          title={attachment.filename}
          className="h-[80vh] w-full rounded-md border border-border"
        />
      ) : null}
    </figure>
  )
}
