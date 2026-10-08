import { http } from '@/lib/http'

export type AgentName = 'documents' | 'email' | 'finance'

export interface Thread {
  id: string
  title: string
  agent: AgentName
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

export interface Me {
  id: string
  email: string
  agents: AgentName[]
}

export interface InvoiceSummary {
  id: string
  from: string
  subject: string
  sentAt: string
}

export interface InvoiceAttachment {
  id: string
  filename: string
  sizeBytes: number
  /** Set when ingest kept only the metadata, e.g. `too_large`. */
  skippedReason: string | null
}

export interface InvoiceDetail extends InvoiceSummary {
  body: string
  attachments: InvoiceAttachment[]
}

/** Product-level API calls. Auth and error handling live in the http client. */
export const api = {
  getMe: () => http.get<Me>('/me'),

  listThreads: (agent: AgentName) => http.get<Thread[]>(`/threads?agent=${agent}`),

  createThread: (agent: AgentName, title?: string) =>
    http.post<Thread>('/threads', title ? { agent, title } : { agent }),

  getMessages: (threadId: string) => http.get<ThreadMessage[]>(`/threads/${threadId}/messages`),

  listInvoices: () => http.get<InvoiceSummary[]>('/finance/invoices'),

  getInvoice: (emailId: string) => http.get<InvoiceDetail>(`/finance/invoices/${emailId}`),

  getAttachment: (attachmentId: string) => http.getBlob(`/finance/attachments/${attachmentId}`),
}
