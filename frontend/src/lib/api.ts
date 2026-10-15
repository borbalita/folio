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

export type InvoiceStatus = 'open' | 'needs_info' | 'paid'

/** One invoice extracted from an email. `amount` is a decimal string, dates are `YYYY-MM-DD`. */
export interface Invoice {
  id: string
  emailId: string
  attachmentId: string | null
  payee: string | null
  iban: string | null
  bic: string | null
  amount: string | null
  currency: string | null
  invoiceNumber: string | null
  reference: string | null
  invoiceDate: string | null
  dueDate: string | null
  status: InvoiceStatus
  /** Names of the failed checks, e.g. `invalid_iban`. */
  issues: string[]
  paidAt: string | null
  /** `owner` when marked by hand. */
  paidBy: string | null
}

export interface InvoiceRow extends Invoice {
  email: InvoiceSummary
}

export type InvoiceField =
  | 'payee'
  | 'iban'
  | 'bic'
  | 'amount'
  | 'currency'
  | 'invoiceNumber'
  | 'reference'
  | 'invoiceDate'
  | 'dueDate'

/** Only the fields sent change; null clears one. */
export type InvoiceEdit = Partial<Record<InvoiceField, string | null>>

export interface InvoiceDetail extends InvoiceSummary {
  body: string
  attachments: InvoiceAttachment[]
  invoices: Invoice[]
}

export type BankName = 'N26' | 'ING' | 'PayPal'

export interface BankAccount {
  id: string
  name: string | null
  ibanMasked: string | null
  currency: string | null
}

export type ConnectionStatus = 'active' | 'expiring' | 'expired'

export interface BankConnection {
  bank: BankName
  connected: boolean
  validUntil: string | null
  /** Null when the bank was never connected. */
  status: ConnectionStatus | null
  accounts: BankAccount[]
}

export interface Transaction {
  id: string
  /** Booking day, `YYYY-MM-DD`. */
  date: string
  bank: BankName
  accountName: string | null
  counterparty: string | null
  /** Signed decimal string; negative when money left the account. */
  amount: string
  currency: string
}

export interface BankSyncCounts {
  accounts: number
  fetched: number
  added: number
  skipped: number
  unparsed: number
}

/** Product-level API calls. Auth and error handling live in the http client. */
export const api = {
  getMe: () => http.get<Me>('/me'),

  listThreads: (agent: AgentName) => http.get<Thread[]>(`/threads?agent=${agent}`),

  createThread: (agent: AgentName, title?: string) =>
    http.post<Thread>('/threads', title ? { agent, title } : { agent }),

  getMessages: (threadId: string) => http.get<ThreadMessage[]>(`/threads/${threadId}/messages`),

  listInvoices: () => http.get<InvoiceRow[]>('/finance/invoices'),

  updateInvoice: (invoiceId: string, edit: InvoiceEdit) =>
    http.patch<Invoice>(`/finance/invoices/items/${invoiceId}`, edit),

  setInvoicesPaid: (ids: string[], paid: boolean) =>
    http.post<Invoice[]>('/finance/invoices/items/paid', { ids, paid }),

  getInvoice: (emailId: string) => http.get<InvoiceDetail>(`/finance/invoices/${emailId}`),

  listBankConnections: () => http.get<BankConnection[]>('/finance/bank-connections'),

  startBankConnection: (bank: BankName) =>
    http.post<{ url: string }>(`/finance/bank-connections/${bank}/start`),

  completeBankConnection: (code: string, state: string) =>
    http.post<BankConnection[]>('/finance/bank-connections/callback', { code, state }),

  syncBanks: () => http.post<BankSyncCounts>('/finance/bank-sync'),

  listTransactions: () => http.get<Transaction[]>('/finance/transactions'),

  getAttachment: (attachmentId: string) => http.getBlob(`/finance/attachments/${attachmentId}`),
}
