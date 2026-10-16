import { Fragment } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

interface Props {
  /** Where the page sits, after "Invoices"; the last item is the current page. */
  trail: string[]
}

/** "Invoices / …" above a finance page; Invoices goes back to the list as it was left. */
export function Breadcrumb({ trail }: Props) {
  const navigate = useNavigate()
  const location = useLocation()
  // Coming from the list, going back keeps its filters; a direct link opens it fresh.
  const toInvoices = () =>
    location.key === 'default' ? navigate('/finance/invoices') : navigate(-1)

  return (
    <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 text-sm">
      <button
        type="button"
        onClick={toInvoices}
        className="text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
      >
        Invoices
      </button>
      {trail.map((item, index) => (
        <Fragment key={index}>
          <span aria-hidden className="text-muted-foreground">
            /
          </span>
          <span
            className="truncate"
            aria-current={index === trail.length - 1 ? 'page' : undefined}
          >
            {item}
          </span>
        </Fragment>
      ))}
    </nav>
  )
}
