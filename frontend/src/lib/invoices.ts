import type { Invoice, InvoiceStatus } from '@/lib/api'

export interface Filters {
  statuses: InvoiceStatus[]
  /** `YYYY-MM-DD` bounds on the invoice date, or the sent date when it has none. */
  from: string
  to: string
  payee: string
}

export const DEFAULT_FILTERS: Filters = {
  statuses: ['open', 'needs_info'],
  from: '',
  to: '',
  payee: '',
}

export const STATUS_LABELS: Record<InvoiceStatus, string> = {
  open: 'Open',
  needs_info: 'Needs info',
  paid: 'Paid',
}

const ISSUE_LABELS: Record<string, string> = {
  missing_payee: 'No payee',
  missing_iban: 'No IBAN',
  invalid_iban: 'IBAN is not valid',
  missing_amount: 'No amount',
  amount_not_positive: 'Amount is not above zero',
  currency_not_eur: 'Currency is not EUR',
  extraction_failed: 'Extraction failed',
  no_invoice_found: 'No invoice found in this email',
}

export function describeIssue(issue: string): string {
  return ISSUE_LABELS[issue] ?? issue
}

/** Today as `YYYY-MM-DD` in local time, comparable with invoice dates. */
export function todayIso(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

export function isOverdue(invoice: Invoice, today: string): boolean {
  return invoice.status !== 'paid' && invoice.dueDate !== null && invoice.dueDate < today
}

export function formatAmount(amount: string | null, currency: string | null): string | null {
  if (amount === null) {
    return null
  }
  const value = Number(amount)
  if (!currency) {
    return value.toFixed(2)
  }
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(value)
  } catch {
    // Not an ISO currency code the browser knows.
    return `${value.toFixed(2)} ${currency}`
  }
}
