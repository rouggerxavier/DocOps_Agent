import { lazy, Suspense, useEffect, useState } from 'react'

const Scene = lazy(() => import('./ParticlesScene'))

export function ParticlesBackground() {
  const [enabled, setEnabled] = useState(false)

  useEffect(() => {
    // Disable on mobile / small screens for performance
    const mqSize = window.matchMedia('(min-width: 768px)')
    // Disable when user prefers reduced motion
    const mqMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setEnabled(mqSize.matches && !mqMotion.matches)
    update()
    mqSize.addEventListener('change', update)
    mqMotion.addEventListener('change', update)
    return () => {
      mqSize.removeEventListener('change', update)
      mqMotion.removeEventListener('change', update)
    }
  }, [])

  if (!enabled) return null

  return (
    <Suspense fallback={null}>
      <Scene />
    </Suspense>
  )
}
