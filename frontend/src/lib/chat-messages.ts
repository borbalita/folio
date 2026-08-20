import type { UIMessage } from 'ai'

import type { ThreadMessage } from '@/lib/api'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function textPartsFromMessage(message: unknown): UIMessage['parts'] {
  if (!isRecord(message)) {
    return [{ type: 'text', text: '' }]
  }

  const parts = message.parts
  if (Array.isArray(parts)) {
    const textParts: UIMessage['parts'] = []
    for (const part of parts) {
      if (isRecord(part) && part.type === 'text' && typeof part.text === 'string') {
        textParts.push({ type: 'text', text: part.text })
      }
    }
    if (textParts.length > 0) {
      return textParts
    }
  }

  if (typeof message.content === 'string') {
    return [{ type: 'text', text: message.content }]
  }

  return [{ type: 'text', text: '' }]
}

function roleFrom(row: ThreadMessage, message: unknown): UIMessage['role'] {
  if (
    isRecord(message) &&
    (message.role === 'user' || message.role === 'assistant' || message.role === 'system')
  ) {
    return message.role
  }
  return row.role
}

/** Unwrap stored chat_messages rows into AI SDK UIMessage values. */
export function toUIMessages(rows: ThreadMessage[]): UIMessage[] {
  return rows.map((row) => {
    const raw = row.message
    const id = isRecord(raw) && typeof raw.id === 'string' && raw.id ? raw.id : row.id
    return {
      id,
      role: roleFrom(row, raw),
      parts: textPartsFromMessage(raw),
    }
  })
}
