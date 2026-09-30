import { createContext, useContext } from 'react'

import type { Me } from '@/lib/api'

export const MeContext = createContext<Me | null>(null)

/** The signed-in user's profile from `/me`, including which agents they may open. */
export function useMe(): Me {
  const value = useContext(MeContext)
  if (!value) {
    throw new Error('useMe must be used within MeGate')
  }
  return value
}
