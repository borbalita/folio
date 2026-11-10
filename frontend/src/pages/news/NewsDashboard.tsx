import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'

import { NewsStoryCard } from '@/components/news/NewsStoryCard'
import { Button } from '@/components/ui/button'
import { api, type NewsDay, type NewsStory } from '@/lib/api'
import { formatIsoDay } from '@/lib/format'
import { describeApiError } from '@/lib/http'
import type { ChatOutletContext } from '@/pages/chat/ChatPage'

type Filter = 'all' | 'big' | 'security'

const FILTER_LABELS: Record<Filter, string> = { all: 'All', big: 'Big', security: 'Security' }
const EMPTY_TEXT: Record<Filter, string> = {
  all: 'No stories in this period.',
  big: 'No big stories in this period.',
  security: 'No security stories in this period.',
}

interface State {
  days: NewsDay[]
  nextBefore: string | null
  loading: boolean
  error: string | null
}

const EMPTY: State = { days: [], nextBefore: null, loading: true, error: null }

/** A story sits on its newest day, so older pages never repeat a day or a story: pages append. */
export function NewsDashboard() {
  const [filter, setFilter] = useState<Filter>('all')
  const [state, setState] = useState<State>(EMPTY)
  const latest = useRef(0)
  const { agent, refreshThreads } = useOutletContext<ChatOutletContext>()
  const navigate = useNavigate()
  const [opening, setOpening] = useState(false)
  const [chatError, setChatError] = useState<string | null>(null)

  async function openChat(story: NewsStory) {
    setOpening(true)
    setChatError(null)
    try {
      const thread = await api.createThread('news', story.title.slice(0, 255), story.items)
      await refreshThreads()
      void navigate(`${agent.path}/${thread.id}`, { state: { firstMessage: 'Explain this story' } })
    } catch (caught: unknown) {
      setChatError(describeApiError(caught))
    } finally {
      setOpening(false)
    }
  }

  const load = useCallback(
    async (before: string | undefined, replace: boolean) => {
      // A slower answer to an earlier filter must not replace the current one.
      const request = ++latest.current
      setState((current) => ({ ...(replace ? EMPTY : current), loading: true, error: null }))
      try {
        const page = await api.listNewsStories({
          before,
          only: filter === 'all' ? undefined : filter,
        })
        if (request !== latest.current) {
          return
        }
        setState((current) => ({
          days: replace ? page.days : [...current.days, ...page.days],
          nextBefore: page.nextBefore,
          loading: false,
          error: null,
        }))
      } catch (caught: unknown) {
        if (request !== latest.current) {
          return
        }
        setState((current) => ({ ...current, loading: false, error: describeApiError(caught) }))
      }
    },
    [filter],
  )

  useEffect(() => {
    void load(undefined, true)
  }, [load])

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6">
      <div className="mx-auto flex max-w-3xl flex-col gap-6">
        <div className="flex flex-wrap items-center justify-between gap-2 sm:gap-4">
          <h1 className="text-lg font-medium">AI News</h1>
          <div className="flex gap-1" role="group" aria-label="Filter stories">
            {(['all', 'big', 'security'] as const).map((value) => (
              <Button
                key={value}
                size="sm"
                variant={filter === value ? 'default' : 'outline'}
                aria-pressed={filter === value}
                onClick={() => {
                  setFilter(value)
                }}
              >
                {FILTER_LABELS[value]}
              </Button>
            ))}
          </div>
        </div>
        {state.error ? <p className="text-sm text-destructive">{state.error}</p> : null}
        {chatError ? <p className="text-sm text-destructive">{chatError}</p> : null}
        {state.days.map((day) => (
          <section key={day.date} className="flex flex-col gap-2">
            <h2 className="text-sm font-medium text-muted-foreground">
              {formatIsoDay(day.date) ?? day.date}
            </h2>
            <ul className="flex flex-col gap-2">
              {day.stories.map((story) => (
                <NewsStoryCard
                  key={story.key}
                  story={story}
                  chatDisabled={opening}
                  onChat={(chosen) => {
                    void openChat(chosen)
                  }}
                />
              ))}
            </ul>
          </section>
        ))}
        {!state.loading && !state.error && state.days.length === 0 ? (
          <p className="text-sm text-muted-foreground">{EMPTY_TEXT[filter]}</p>
        ) : null}
        {state.loading ? <p className="text-sm text-muted-foreground">Loading…</p> : null}
        {state.nextBefore && !state.loading ? (
          <Button
            variant="outline"
            className="self-start"
            onClick={() => {
              void load(state.nextBefore ?? undefined, false)
            }}
          >
            Load older
          </Button>
        ) : null}
      </div>
    </div>
  )
}
