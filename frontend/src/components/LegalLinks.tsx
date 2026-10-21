import { Link } from 'react-router-dom'

import { IMPRINT_URL } from '@/lib/legal'
import { cn } from '@/lib/utils'

export function LegalLinks({ className }: { className?: string }) {
  return (
    <nav aria-label="Legal" className={cn('flex gap-3 text-xs text-muted-foreground', className)}>
      <a href={IMPRINT_URL} className="hover:text-foreground hover:underline">
        Imprint
      </a>
      <span aria-hidden>·</span>
      <Link to="/privacy" className="hover:text-foreground hover:underline">
        Privacy
      </Link>
    </nav>
  )
}
