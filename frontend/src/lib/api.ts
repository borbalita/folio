import { http } from '@/lib/http'

export interface Thread {
  id: string
  title: string
  createdAt: string
  updatedAt: string
}

export interface ThreadMessage {
  id: string
  role: 'user' | 'assistant'
  /** AI SDK-compatible message JSON, stored as-is by the backend. */
  message: unknown
  sequenceNumber: number
  createdAt: string
}

/** Product-level API calls. Auth and error handling live in the http client. */
export const api = {
  listThreads: () => http.get<Thread[]>('/threads'),

  createThread: (title?: string) => http.post<Thread>('/threads', title ? { title } : {}),

  getMessages: (threadId: string) => http.get<ThreadMessage[]>(`/threads/${threadId}/messages`),
}
