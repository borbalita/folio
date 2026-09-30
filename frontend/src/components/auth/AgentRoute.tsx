import { Navigate, Outlet } from 'react-router-dom'

import type { AgentName } from '@/lib/api'
import { useMe } from '@/lib/me'

/** Sends a user who may not open this agent back to the picker. */
export function AgentRoute({ agent }: { agent: AgentName }) {
  const { agents } = useMe()
  if (!agents.includes(agent)) {
    return <Navigate to="/" replace />
  }
  return <Outlet />
}
