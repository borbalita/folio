import { ChevronDown, ChevronRight, MessageSquare } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import type { NewsStory } from '@/lib/api'

interface NewsStoryCardProps {
  story: NewsStory
  chatDisabled: boolean
  onChat: (story: NewsStory) => void
}

export function NewsStoryCard({ story, chatDisabled, onChat }: NewsStoryCardProps) {
  const [open, setOpen] = useState(false)
  const Chevron = open ? ChevronDown : ChevronRight
  return (
    <li className="rounded-md border border-border p-3">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-medium">{story.title}</h3>
            {story.badges.includes('big') ? (
              <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                Big
              </span>
            ) : null}
            {story.badges.includes('security') ? (
              <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-medium text-destructive">
                Security
              </span>
            ) : null}
          </div>
          {story.blurb ? (
            <p className="mt-1 text-sm text-muted-foreground">{story.blurb}</p>
          ) : null}
          {story.links.length > 0 ? (
            <p className="mt-2 flex flex-wrap gap-x-3 text-xs">
              {story.links.map((link) => (
                <a
                  key={link.source}
                  href={link.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary hover:underline"
                >
                  {link.name}
                </a>
              ))}
            </p>
          ) : null}
        </div>
        <Button
          size="sm"
          variant="outline"
          disabled={chatDisabled}
          onClick={() => {
            onChat(story)
          }}
        >
          <MessageSquare className="size-3.5" />
          Chat
        </Button>
        {story.explanation ? (
          <button
            type="button"
            aria-expanded={open}
            onClick={() => {
              setOpen((current) => !current)
            }}
            className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <Chevron className="size-3.5" />
            Explanation
          </button>
        ) : null}
      </div>
      {open && story.explanation ? (
        <p className="mt-3 border-t border-border pt-3 text-sm whitespace-pre-line">
          {story.explanation}
        </p>
      ) : null}
    </li>
  )
}
