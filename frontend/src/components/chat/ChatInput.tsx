import { type FormEvent, type KeyboardEvent, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

interface ChatInputProps {
  disabled: boolean
  onSend: (text: string) => void
}

export function ChatInput({ disabled, onSend }: ChatInputProps) {
  const [input, setInput] = useState('')

  function submit() {
    const text = input.trim()
    if (!text || disabled) {
      return
    }
    onSend(text)
    setInput('')
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    submit()
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form className="border-t p-3" onSubmit={onSubmit}>
      <div className="mx-auto flex max-w-2xl items-end gap-2">
        <Textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={onKeyDown}
          disabled={disabled}
          placeholder="Ask about a filing…"
          rows={2}
          className="min-h-10 resize-none"
        />
        <Button type="submit" disabled={disabled || input.trim() === ''}>
          Send
        </Button>
      </div>
    </form>
  )
}
