import { Navigate, Outlet } from 'react-router-dom'

import { useAuth } from '@/lib/auth'

export function ProtectedRoute() {
  const { status } = useAuth()

  if (status === 'loading') {
    return (
      <main className="flex min-h-screen items-center justify-center p-8 text-muted-foreground">
        Loading…
      </main>
    )
  }

  if (status === 'unauthenticated') {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}
