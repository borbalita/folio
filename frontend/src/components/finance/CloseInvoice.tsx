import { XIcon } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'

/** Closes the invoice: back to the list as it was left, or to a fresh list from a direct link. */
export function CloseInvoice() {
  const navigate = useNavigate()
  const location = useLocation()
  const close = () =>
    location.key === 'default' ? navigate('/finance/invoices') : navigate(-1)

  return (
    <Button variant="ghost" size="icon" aria-label="Close invoice" title="Close" onClick={close}>
      <XIcon />
    </Button>
  )
}
