import { useCallback, useEffect, useRef, useState } from 'react'

import { api } from '@/lib/api'
import { ApiError, describeApiError } from '@/lib/http'

const REALTIME_CALLS_URL = 'https://api.openai.com/v1/realtime/calls'

export type CallStatus = 'idle' | 'connecting' | 'live' | 'ended'
export type EndReason = 'hangup' | 'timeout' | 'dropped' | 'error'

export interface TranscriptLine {
  /** The Realtime conversation item id. */
  id: string
  speaker: 'you' | 'them'
  /** Empty while the words are still being transcribed. */
  text: string
}

interface Connection {
  pc: RTCPeerConnection
  mic: MediaStream
  audio: HTMLAudioElement
}

/** The Realtime server events this page reads; everything else is ignored. */
type ServerEvent =
  | { type: 'input_audio_buffer.committed'; item_id: string }
  | { type: 'conversation.item.input_audio_transcription.completed'; item_id: string; transcript: string }
  | { type: 'response.output_audio_transcript.delta'; item_id: string; delta: string }
  | { type: 'error'; error: { message: string } }

function describeStartError(caught: unknown): string {
  if (caught instanceof DOMException && caught.name === 'NotAllowedError') {
    return 'Microphone access was blocked. Allow it in your browser to take the call.'
  }
  if (caught instanceof DOMException && caught.name === 'NotFoundError') {
    return 'No microphone found.'
  }
  if (caught instanceof ApiError && caught.status === 429) {
    return "That's a lot of calls for one hour. Try again later."
  }
  if (caught instanceof ApiError) {
    return describeApiError(caught)
  }
  return "The call couldn't connect. Try again in a moment."
}

function upsertLine(
  lines: TranscriptLine[],
  id: string,
  speaker: TranscriptLine['speaker'],
  update: (text: string) => string,
): TranscriptLine[] {
  const index = lines.findIndex((line) => line.id === id)
  if (index === -1) {
    return [...lines, { id, speaker, text: update('') }]
  }
  return lines.map((line, i) => (i === index ? { ...line, text: update(line.text) } : line))
}

/** One voice call with a persona: the browser talks to OpenAI Realtime over WebRTC. */
export function useRealtimeCall() {
  const [status, setStatus] = useState<CallStatus>('idle')
  const [endReason, setEndReason] = useState<EndReason | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lines, setLines] = useState<TranscriptLine[]>([])
  const [elapsed, setElapsed] = useState(0)
  const [maxSeconds, setMaxSeconds] = useState<number | null>(null)
  const [muted, setMuted] = useState(false)
  const connection = useRef<Connection | null>(null)
  // Bumped by every start and end, so a start still awaiting knows it was hung up on.
  const attempt = useRef(0)

  const end = useCallback((reason: EndReason) => {
    attempt.current += 1
    const current = connection.current
    connection.current = null
    if (current) {
      current.pc.close()
      current.mic.getTracks().forEach((track) => {
        track.stop()
      })
      current.audio.srcObject = null
    }
    setStatus((previous) => (previous === 'idle' ? previous : 'ended'))
    setEndReason((previous) => previous ?? reason)
  }, [])

  const handleEvent = useCallback(
    (event: ServerEvent) => {
      switch (event.type) {
        case 'input_audio_buffer.committed':
          // Reserves the user's place in the transcript; their words arrive after the reply starts.
          setLines((previous) => upsertLine(previous, event.item_id, 'you', (text) => text))
          break
        case 'conversation.item.input_audio_transcription.completed':
          setLines((previous) =>
            upsertLine(previous, event.item_id, 'you', () => event.transcript.trim()),
          )
          break
        case 'response.output_audio_transcript.delta':
          setLines((previous) =>
            upsertLine(previous, event.item_id, 'them', (text) => text + event.delta),
          )
          break
        case 'error':
          setError(event.error.message)
          break
      }
    },
    [],
  )

  const start = useCallback(
    async (personaId: string) => {
      const mine = ++attempt.current
      setStatus('connecting')
      setEndReason(null)
      setError(null)
      setLines([])
      setElapsed(0)
      setMuted(false)
      let mic: MediaStream | null = null
      try {
        mic = await navigator.mediaDevices.getUserMedia({ audio: true })
        const session = await api.createPhoneSession(personaId)
        if (attempt.current !== mine) {
          mic.getTracks().forEach((track) => {
            track.stop()
          })
          return
        }

        const pc = new RTCPeerConnection()
        const audio = new Audio()
        audio.autoplay = true
        pc.ontrack = (event) => {
          audio.srcObject = event.streams[0] ?? null
        }
        mic.getTracks().forEach((track) => {
          pc.addTrack(track, mic as MediaStream)
        })
        connection.current = { pc, mic, audio }

        const channel = pc.createDataChannel('oai-events')
        channel.onopen = () => {
          // The persona placed the call, so they speak first.
          channel.send(JSON.stringify({ type: 'response.create' }))
          setStatus('live')
        }
        channel.onmessage = (message: MessageEvent<string>) => {
          handleEvent(JSON.parse(message.data) as ServerEvent)
        }
        pc.onconnectionstatechange = () => {
          if (pc.connectionState === 'failed') {
            end('dropped')
          }
        }

        const offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        const response = await fetch(REALTIME_CALLS_URL, {
          method: 'POST',
          body: offer.sdp,
          headers: { Authorization: `Bearer ${session.secret}`, 'Content-Type': 'application/sdp' },
        })
        if (!response.ok) {
          throw new Error(`Realtime call failed: ${response.status}`)
        }
        if (attempt.current !== mine) {
          return
        }
        await pc.setRemoteDescription({ type: 'answer', sdp: await response.text() })
        setMaxSeconds(session.maxSeconds)
      } catch (caught: unknown) {
        if (attempt.current !== mine) {
          mic?.getTracks().forEach((track) => {
            track.stop()
          })
          return
        }
        if (!connection.current) {
          mic?.getTracks().forEach((track) => {
            track.stop()
          })
        }
        setError(describeStartError(caught))
        end('error')
      }
    },
    [end, handleEvent],
  )

  useEffect(() => {
    if (status !== 'live') {
      return
    }
    const timer = window.setInterval(() => {
      setElapsed((seconds) => seconds + 1)
    }, 1000)
    return () => {
      window.clearInterval(timer)
    }
  }, [status])

  useEffect(() => {
    if (status !== 'live' || maxSeconds === null) {
      return
    }
    const timeout = window.setTimeout(() => {
      end('timeout')
    }, maxSeconds * 1000)
    return () => {
      window.clearTimeout(timeout)
    }
  }, [status, maxSeconds, end])

  // Leaving the page mid-call hangs up and frees the mic.
  useEffect(
    () => () => {
      end('hangup')
    },
    [end],
  )

  const toggleMute = useCallback(() => {
    const current = connection.current
    if (!current) {
      return
    }
    setMuted((wasMuted) => {
      current.mic.getAudioTracks().forEach((track) => {
        track.enabled = wasMuted
      })
      return !wasMuted
    })
  }, [])

  const hangUp = useCallback(() => {
    end('hangup')
  }, [end])

  return { status, endReason, error, lines, elapsed, maxSeconds, muted, start, hangUp, toggleMute }
}
