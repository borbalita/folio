import { useEffect } from 'react'

const REFRESH_MS = 5000

/** Calls `refresh` every 5 s while the tab is visible, and when the window regains focus. */
export function useRefresh(refresh: () => void) {
  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === 'visible') {
        refresh()
      }
    }
    const timer = window.setInterval(tick, REFRESH_MS)
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', tick)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [refresh])
}
