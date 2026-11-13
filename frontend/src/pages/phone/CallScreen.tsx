import { LoaderCircle, Mic, MicOff, Phone, PhoneOff } from 'lucide-react'
import { useEffect, useRef } from 'react'

import { Button } from '@/components/ui/button'
import type { PhonePersona } from '@/lib/api'
import { startRingtone } from '@/lib/ringtone'
import { useRealtimeCall, type EndReason } from '@/lib/useRealtimeCall'
import { cn } from '@/lib/utils'

const END_MESSAGES: Record<EndReason, string> = {
  hangup: 'Call ended.',
  timeout: 'Time is up for this call.',
  dropped: 'The call dropped.',
  error: "The call couldn't connect.",
}

function clock(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`
}

function RoundButton({
  label,
  className,
  onClick,
  children,
}: {
  label: string
  className: string
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className={cn(
        'flex size-14 items-center justify-center rounded-full text-white shadow-md outline-none focus-visible:ring-3 focus-visible:ring-ring/50 [&_svg]:size-6',
        className,
      )}
    >
      {children}
    </button>
  )
}

export function CallScreen({ persona, onClose }: { persona: PhonePersona; onClose: () => void }) {
  const call = useRealtimeCall()
  const transcriptEnd = useRef<HTMLDivElement>(null)
  const ringing = call.status === 'idle'

  useEffect(() => {
    if (!ringing) {
      return
    }
    return startRingtone()
  }, [ringing])

  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ block: 'end' })
  }, [call.lines])

  const remaining = call.maxSeconds === null ? null : Math.max(call.maxSeconds - call.elapsed, 0)

  return (
    <div className="flex w-full max-w-md flex-col items-center gap-6">
      <div className="flex flex-col items-center gap-3 text-center">
        <span
          className={cn(
            'flex size-20 items-center justify-center rounded-full bg-ring/12 font-heading text-2xl font-semibold text-ring',
            ringing && 'animate-pulse motion-reduce:animate-none',
          )}
          aria-hidden
        >
          {persona.name.charAt(0)}
        </span>
        <h1 className="font-heading text-2xl font-semibold">{persona.name}</h1>
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {ringing ? 'Incoming call…' : null}
          {call.status === 'connecting' ? 'Connecting…' : null}
          {call.status === 'live'
            ? `${clock(call.elapsed)}${remaining !== null && remaining <= 30 ? ` · ${remaining}s left` : ''}`
            : null}
          {call.status === 'ended' && call.endReason ? END_MESSAGES[call.endReason] : null}
        </p>
      </div>

      {call.lines.length > 0 ? (
        <div
          className="flex max-h-80 w-full flex-col gap-2 overflow-y-auto rounded-xl border border-border bg-card p-4 text-sm"
          aria-label="Transcript"
        >
          {call.lines.map((line) => (
            <p key={line.id} className={line.speaker === 'you' ? 'text-right' : undefined}>
              <span className="font-semibold">{line.speaker === 'you' ? 'You' : persona.name}: </span>
              <span className={line.text ? undefined : 'text-muted-foreground'}>
                {line.text || '…'}
              </span>
            </p>
          ))}
          <div ref={transcriptEnd} />
        </div>
      ) : null}

      {call.error ? <p className="text-center text-sm text-destructive">{call.error}</p> : null}

      {ringing ? (
        <div className="flex gap-12">
          <RoundButton label="Decline" className="bg-red-600 hover:bg-red-700" onClick={onClose}>
            <PhoneOff />
          </RoundButton>
          <RoundButton
            label="Answer"
            className="bg-green-600 hover:bg-green-700"
            onClick={() => {
              void call.start(persona.id)
            }}
          >
            <Phone />
          </RoundButton>
        </div>
      ) : null}

      {call.status === 'connecting' ? (
        <LoaderCircle className="size-6 animate-spin text-muted-foreground" aria-label="Connecting" />
      ) : null}

      {call.status === 'live' ? (
        <div className="flex gap-12">
          <RoundButton
            label={call.muted ? 'Unmute' : 'Mute'}
            className={call.muted ? 'bg-foreground/70 hover:bg-foreground/80' : 'bg-foreground/40 hover:bg-foreground/50'}
            onClick={call.toggleMute}
          >
            {call.muted ? <MicOff /> : <Mic />}
          </RoundButton>
          <RoundButton label="Hang up" className="bg-red-600 hover:bg-red-700" onClick={call.hangUp}>
            <PhoneOff />
          </RoundButton>
        </div>
      ) : null}

      {call.status === 'ended' ? (
        <div className="flex gap-2">
          <Button variant="outline" onClick={onClose}>
            Back to personas
          </Button>
          <Button
            onClick={() => {
              void call.start(persona.id)
            }}
          >
            Call back
          </Button>
        </div>
      ) : null}
    </div>
  )
}
