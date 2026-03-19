import { useRef, useEffect } from 'react'

/**
 * Tracks page scroll progress as a ref (0 at top → 1 at bottom).
 * Returns a MutableRefObject — read `.current` in animation loops
 * without triggering React re-renders.
 */
export function useScrollProgress() {
  const progress = useRef(0)

  useEffect(() => {
    const update = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight
      progress.current = max > 0 ? Math.min(window.scrollY / max, 1) : 0
    }
    window.addEventListener('scroll', update, { passive: true })
    update()
    return () => window.removeEventListener('scroll', update)
  }, [])

  return progress
}
