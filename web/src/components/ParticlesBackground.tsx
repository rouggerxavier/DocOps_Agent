import { lazy, Suspense, useEffect, useState } from 'react'

const Scene = lazy(() => import('./ParticlesScene'))

export function ParticlesBackground() {
  const [enabled, setEnabled] = useState(false)

  useEffect(() => {
    // Disable on mobile / small screens for performance
    const mq = window.matchMedia('(min-width: 768px)')
    const update = () => setEnabled(mq.matches)
    update()
    mq.addEventListener('change', update)
    return () => mq.removeEventListener('change', update)
  }, [])

  if (!enabled) return null

  return (
    <Suspense fallback={null}>
      <Scene />
    </Suspense>
  )
}
