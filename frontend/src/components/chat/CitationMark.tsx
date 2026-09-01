import { cn } from '@/lib/utils'

interface CitationMarkProps {
  index: number
  selected: boolean
  onSelect: (citationIndex: number) => void
}

export function CitationMark({ index, selected, onSelect }: CitationMarkProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      aria-label={`Open source ${index}`}
      onClick={() => {
        onSelect(index)
      }}
      className={cn(
        'mx-0.5 inline-flex translate-y-px items-center rounded-sm px-1 py-px text-[0.75em] font-medium tabular-nums',
        'outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50',
        selected
          ? 'bg-citation text-citation-foreground'
          : 'bg-citation/15 text-citation hover:bg-citation/25',
      )}
    >
      [{index}]
    </button>
  )
}
