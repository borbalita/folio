import { useCallback, useState } from 'react'

import { Button } from '@/components/ui/button'
import { api, type DemoPayment } from '@/lib/api'
import { describeApiError } from '@/lib/http'
import { formatAmount, STATUS_LABELS } from '@/lib/invoices'
import { useRefresh } from '@/lib/useRefresh'

export function BookPaymentsBlock({ initial }: { initial: DemoPayment[] }) {
  const [payments, setPayments] = useState<DemoPayment[]>(initial)
  const [booking, setBooking] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const refresh = useCallback(() => {
    api
      .listDemoPayments()
      .then(setPayments)
      .catch(() => undefined)
  }, [])
  useRefresh(refresh)

  async function book(payment: DemoPayment) {
    setBooking(payment.id)
    setMessage(null)
    try {
      const result = await api.bookDemoPayment(payment.id)
      setMessage(
        result.booked
          ? `Booked ${payment.payee}: invoice ${result.invoiceStatus ? STATUS_LABELS[result.invoiceStatus].toLowerCase() : 'unchanged'}.`
          : `${payment.payee} was already booked.`,
      )
      refresh()
    } catch (caught: unknown) {
      setMessage(describeApiError(caught))
    } finally {
      setBooking(null)
    }
  }

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-border p-4">
      <h2 className="font-heading text-base font-semibold">Payments to book</h2>
      {payments.length === 0 ? (
        <p className="text-sm text-muted-foreground">No approved payments yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {payments.map((payment) => (
            <li key={payment.id} className="flex items-center justify-between gap-3 text-sm">
              <span className="min-w-0">
                <span className="block truncate">{payment.payee}</span>
                <span className="text-muted-foreground">
                  {formatAmount(payment.amount, payment.currency)}
                </span>
              </span>
              <Button
                size="sm"
                disabled={booking !== null}
                onClick={() => void book(payment)}
              >
                {booking === payment.id ? 'Booking…' : 'Book'}
              </Button>
            </li>
          ))}
        </ul>
      )}
      {message ? <p className="text-sm">{message}</p> : null}
    </section>
  )
}
