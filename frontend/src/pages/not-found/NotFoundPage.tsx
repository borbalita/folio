import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'

export function NotFoundPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8">
      <h1 className="text-2xl font-semibold">404</h1>
      <p className="text-muted-foreground">This page does not exist.</p>
      <Button render={<Link to="/chat" />}>Go to chat</Button>
    </main>
  )
}
