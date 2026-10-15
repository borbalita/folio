import type { ReactNode } from 'react'

const URL_PATTERN = /https?:\/\/[^\s<>"]+/g

/** Text with its http(s) links clickable; trailing punctuation stays outside the link. */
function withLinks(line: string): ReactNode[] {
  const nodes: ReactNode[] = []
  let last = 0
  for (const match of line.matchAll(URL_PATTERN)) {
    const url = match[0].replace(/[.,;:!?)\]]+$/, '')
    const start = match.index
    nodes.push(line.slice(last, start))
    nodes.push(
      <a
        key={start}
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="break-all text-primary underline underline-offset-2"
      >
        {url}
      </a>,
    )
    last = start + url.length
  }
  nodes.push(line.slice(last))
  return nodes
}

/** An email body as stored at ingest: paragraphs and line breaks kept, quoted lines muted. */
export function EmailMessage({ body }: { body: string }) {
  if (!body.trim()) {
    return <p className="text-sm text-muted-foreground">No text in this email.</p>
  }
  return (
    <div className="flex flex-col text-sm leading-relaxed">
      {body.split('\n').map((line, index) =>
        line === '' ? (
          <div key={index} className="h-3" />
        ) : (
          <p
            key={index}
            className={line.startsWith('>') ? 'text-muted-foreground' : undefined}
          >
            {withLinks(line)}
          </p>
        ),
      )}
    </div>
  )
}
