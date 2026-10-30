import type { DisplayStatus, Invoice } from '@/lib/api'

export interface Filters {
  statuses: DisplayStatus[]
  /** `YYYY-MM-DD` bounds on the invoice date, or the sent date when it has none. */
  from: string
  to: string
  payee: string
}

export const DEFAULT_FILTERS: Filters = {
  statuses: ['open', 'pending', 'needs_info'],
  from: '',
  to: '',
  payee: '',
}

export const STATUS_LABELS: Record<DisplayStatus, string> = {
  open: 'Open',
  pending: 'Pending',
  needs_info: 'Needs info',
  paid: 'Paid',
}

export function displayStatus(invoice: Invoice): DisplayStatus {
  return invoice.status === 'open' && invoice.paymentPending ? 'pending' : invoice.status
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
  invoice_online:
    'The invoice is only available online: download it, or check whether you have to pay',
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

/** German invoices write 1.234,56; the API takes 1234.56. */
export function parseAmount(value: string): string {
  return value.includes(',') ? value.replace(/\./g, '').replace(',', '.') : value
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
