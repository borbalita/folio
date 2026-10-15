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
  /** `owner` when marked by hand, `match` when a bank transaction is linked. */
  paidBy: string | null
  /** The linked payment, set when `paidBy` is `match`. */
  match: InvoiceMatch | null
  /** Possible payments for the owner to confirm or reject. */
  suggestions: InvoiceMatch[]
}

export type MatchSignal = 'amount' | 'iban' | 'reference' | 'name'

/** A bank transaction linked to, or suggested for, an invoice. `amount` is signed. */
export interface InvoiceMatch {
  id: string
  /** `auto` when the rules linked it, `owner` when confirmed by hand. */
  source: 'auto' | 'owner'
  signals: MatchSignal[]
  transaction: {
    id: string
    date: string
    bank: BankName
    counterparty: string | null
    amount: string
    currency: string
  }
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

export type PaymentDraftStatus = 'draft' | 'approved' | 'completed' | 'cancelled'

/** A payment prepared for an invoice; payee, IBAN, amount and reference are frozen. */
export interface PaymentDraft {
  id: string
  invoiceId: string
  emailId: string
  attachmentId: string | null
  payee: string
  iban: string
  bic: string | null
  amount: string
  currency: string
  reference: string | null
  status: PaymentDraftStatus
  account: { id: string; bank: BankName; name: string | null }
}

export interface ApprovedPayment extends PaymentDraft {
  /** The EPC069-12 text the QR code carries. */
  payload: string
  /** The QR code as an SVG data URI. */
  qr: string
}

export interface PaymentDraftsResult {
  drafts: PaymentDraft[]
  skipped: { invoiceId: string; reason: string }[]
}

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

  confirmMatch: (matchId: string) => http.post<Invoice>(`/finance/matches/${matchId}/confirm`),

  rejectMatch: (matchId: string) => http.post<Invoice>(`/finance/matches/${matchId}/reject`),

  createPaymentDrafts: (invoiceIds: string[], accountId: string) =>
    http.post<PaymentDraftsResult>('/finance/payment-drafts', { invoiceIds, accountId }),

  getPaymentDrafts: (ids: string[]) =>
    http.get<PaymentDraft[]>(
      `/finance/payment-drafts?${ids.map((id) => `ids=${encodeURIComponent(id)}`).join('&')}`,
    ),

  approvePaymentDraft: (id: string) =>
    http.post<ApprovedPayment>(`/finance/payment-drafts/${id}/approve`),

  cancelPaymentDraft: (id: string) =>
    http.post<PaymentDraft>(`/finance/payment-drafts/${id}/cancel`),

  listBankConnections: () => http.get<BankConnection[]>('/finance/bank-connections'),

  startBankConnection: (bank: BankName) =>
    http.post<{ url: string }>(`/finance/bank-connections/${bank}/start`),

  completeBankConnection: (code: string, state: string) =>
    http.post<BankConnection[]>('/finance/bank-connections/callback', { code, state }),

  syncBanks: () => http.post<BankSyncCounts>('/finance/bank-sync'),

  listTransactions: () => http.get<Transaction[]>('/finance/transactions'),

  getAttachment: (attachmentId: string) => http.getBlob(`/finance/attachments/${attachmentId}`),
}
