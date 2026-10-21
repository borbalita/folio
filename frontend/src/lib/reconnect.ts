import { api, type BankConnection, type BankName } from '@/lib/api'

const QUEUE_KEY = 'finance.reconnectQueue'
const DAY_MS = 24 * 60 * 60 * 1000

/** True when the bank needs the owner's approval again soon or already. */
export function needsReconnect(connection: BankConnection): boolean {
  return connection.status === 'expiring' || connection.status === 'expired'
}

/** "N26 bank access expires in 5 days." / "… has expired.", or null when nothing is due. */
export function expiryMessage(connection: BankConnection): string | null {
  if (connection.status === 'expired') {
    return `${connection.bank} bank access has expired.`
  }
  if (connection.status === 'expiring' && connection.validUntil) {
    const days = Math.max(1, Math.ceil((Date.parse(connection.validUntil) - Date.now()) / DAY_MS))
    return `${connection.bank} bank access expires in ${days} ${days === 1 ? 'day' : 'days'}.`
  }
  return null
}

/** Leaves the app for the bank's consent page. */
export async function goToBank(bank: BankName): Promise<void> {
  const { url } = await api.startBankConnection(bank)
  window.location.assign(url)
}

// Reconnect all survives the round trips to each bank in sessionStorage. Storage can be
// unavailable (private mode, blocked site data); then only the first bank is reconnected.
function writeQueue(banks: BankName[]): void {
  try {
    if (banks.length === 0) {
      sessionStorage.removeItem(QUEUE_KEY)
    } else {
      sessionStorage.setItem(QUEUE_KEY, JSON.stringify(banks))
    }
  } catch {
    // See above.
  }
}

/** Starts Reconnect all: the first bank now, the rest after each callback. */
export async function reconnectAll(banks: BankName[]): Promise<void> {
  const [first, ...rest] = banks
  if (!first) {
    return
  }
  writeQueue(rest)
  try {
    await goToBank(first)
  } catch (caught) {
    writeQueue([])
    throw caught
  }
}

/** The next bank waiting in Reconnect all, removed from the queue; null when done. */
export function takeNextQueued(): BankName | null {
  let banks: BankName[]
  try {
    banks = JSON.parse(sessionStorage.getItem(QUEUE_KEY) ?? '[]') as BankName[]
  } catch {
    return null
  }
  const [next, ...rest] = banks
  writeQueue(rest)
  return next ?? null
}

export function clearReconnectQueue(): void {
  writeQueue([])
}
