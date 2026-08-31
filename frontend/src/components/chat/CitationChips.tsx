import { citationLabel, type CitationData } from '@/lib/chat-messages'
import { cn } from '@/lib/utils'

interface CitationChipsProps {
  citations: CitationData[]
  selectedIndex: number | null
  onSelect: (citationIndex: number) => void
}

export function CitationChips({ citations, selectedIndex, onSelect }: CitationChipsProps) {
  if (citations.length === 0) {
    return null
  }

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {citations.map((citation) => {
        const selected = selectedIndex === citation.citationIndex
        return (
          <button
            key={`${citation.chunkId}-${citation.citationIndex}`}
            type="button"
            aria-pressed={selected}
            onClick={() => {
              onSelect(citation.citationIndex)
            }}
            className={cn(
              'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs',
              'outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50',
              selected
                ? 'border-citation bg-citation text-citation-foreground'
                : 'border-border bg-background text-muted-foreground hover:text-foreground',
            )}
          >
            <span className="tabular-nums opacity-70">{citation.citationIndex}</span>
            {citationLabel(citation)}
          </button>
        )
      })}
    </div>
  )
}
