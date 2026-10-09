import { Navigate, useParams } from 'react-router-dom'

/** Invoices moved to Finance; old `/email/invoices/:emailId` links still resolve. */
export function LegacyInvoiceRedirect() {
  const { emailId } = useParams<{ emailId: string }>()
  return <Navigate to={`/finance/invoices/${emailId}`} replace />
}
