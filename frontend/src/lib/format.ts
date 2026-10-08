/** Formats a `YYYY-MM-DD` day as a local medium date, or null when it doesn't parse. */
export function formatIsoDay(iso: string | undefined): string | null {
  if (!iso) {
    return null
  }
  const [year, month, day] = iso.split('-').map(Number)
  if (!year || !month || !day) {
    return null
  }
  const date = new Date(year, month - 1, day)
  if (Number.isNaN(date.getTime())) {
    return null
  }
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date)
}

/** Formats an ISO timestamp as a local medium date, or null when it doesn't parse. */
export function formatTimestamp(iso: string): string | null {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return null
  }
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date)
}
