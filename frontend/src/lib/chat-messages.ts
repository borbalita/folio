import type { UIMessage } from 'ai'

import type { ThreadMessage } from '@/lib/api'

export type CitationData = {
  chunkId: string
  citationIndex: number
  excerpt: string | null
  ticker?: string
  companyName?: string
  form?: string
  fiscalYear?: number
  filingDate?: string
  page?: string | null
  section?: string | null
}

export type CopilotUIMessage = UIMessage<unknown, { citation: CitationData }>

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isCitationData(value: unknown): value is CitationData {
  if (!isRecord(value)) {
    return false
  }
  if (typeof value.chunkId !== 'string') {
    return false
  }
  if (typeof value.citationIndex !== 'number') {
    return false
  }
  return value.excerpt === undefined || value.excerpt === null || typeof value.excerpt === 'string'
}

function messagePartsFromMessage(message: unknown): CopilotUIMessage['parts'] {
  if (!isRecord(message)) {
    return [{ type: 'text', text: '' }]
  }

  const parts = message.parts
  if (Array.isArray(parts)) {
    const kept: CopilotUIMessage['parts'] = []
    for (const part of parts) {
      if (isRecord(part) && part.type === 'text' && typeof part.text === 'string') {
        kept.push({ type: 'text', text: part.text })
      }
      if (isRecord(part) && part.type === 'data-citation' && isCitationData(part.data)) {
        kept.push({ type: 'data-citation', data: part.data })
      }
    }
    if (kept.length > 0) {
      return kept
    }
  }

  if (typeof message.content === 'string') {
    return [{ type: 'text', text: message.content }]
  }

  return [{ type: 'text', text: '' }]
}

function roleFrom(row: ThreadMessage, message: unknown): CopilotUIMessage['role'] {
  if (
    isRecord(message) &&
    (message.role === 'user' || message.role === 'assistant' || message.role === 'system')
  ) {
    return message.role
  }
  return row.role
}

/** Unwrap stored chat_messages rows into AI SDK UIMessage values. */
export function toUIMessages(rows: ThreadMessage[]): CopilotUIMessage[] {
  return rows.map((row) => {
    const raw = row.message
    const id = isRecord(raw) && typeof raw.id === 'string' && raw.id ? raw.id : row.id
    return {
      id,
      role: roleFrom(row, raw),
      parts: messagePartsFromMessage(raw),
    }
  })
}

export function textOf(message: CopilotUIMessage): string {
  return message.parts
    .filter((part) => part.type === 'text')
    .map((part) => part.text)
    .join('')
}

export function citationsOf(message: CopilotUIMessage): CitationData[] {
  return message.parts
    .filter((part) => part.type === 'data-citation')
    .map((part) => part.data)
}

export function citationLabel(data: CitationData): string {
  const ticker = data.ticker?.trim()
  const form = data.form?.trim()
  if (ticker && form) {
    return `${ticker} ${form}`
  }
  if (ticker) {
    return ticker
  }
  if (form) {
    return form
  }
  return `Source ${data.citationIndex}`
}
