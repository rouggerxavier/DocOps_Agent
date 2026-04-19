import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { MobileTopNav } from './MobileTopNav'

// These routes use a full-height layout without inner padding/max-width
const FULL_HEIGHT_ROUTES = ['/chat', '/schedule', '/notes']
const DESKTOP_MEDIA_QUERY = '(min-width: 768px)'

export function Layout() {
  const { pathname } = useLocation()
  const isFullHeight = FULL_HEIGHT_ROUTES.includes(pathname)
  const [isDesktop, setIsDesktop] = useState(() =>
    typeof window !== 'undefined'
      ? window.matchMedia(DESKTOP_MEDIA_QUERY).matches
      : false,
  )

  useEffect(() => {
    const mediaQuery = window.matchMedia(DESKTOP_MEDIA_QUERY)
    const legacyMediaQuery = mediaQuery as MediaQueryList & {
      addListener: (listener: (event: MediaQueryListEvent) => void) => void
      removeListener: (listener: (event: MediaQueryListEvent) => void) => void
    }

    const handleChange = (event: MediaQueryListEvent) => {
      setIsDesktop(event.matches)
    }

    setIsDesktop(mediaQuery.matches)

    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', handleChange)
      return () => mediaQuery.removeEventListener('change', handleChange)
    }

    legacyMediaQuery.addListener(handleChange)
    return () => legacyMediaQuery.removeListener(handleChange)
  }, [])

  return (
    <div className="app-editorial flex min-h-screen text-[color:var(--ui-text)]">
      <Sidebar
        mobileOpen={false}
        isDesktop={isDesktop}
        onMobileClose={() => {}}
      />

      <main className="relative z-10 flex flex-1 flex-col overflow-hidden md:pl-72">
        <header className="sticky top-0 z-20 flex h-14 items-center px-4 md:hidden bg-transparent">
          <span className="font-headline text-2xl font-bold tracking-tight text-[color:var(--ui-accent)]">
            DocOps Agent
          </span>
        </header>

        <MobileTopNav />

        {isFullHeight ? (
          <Outlet />
        ) : (
          <div className="mx-auto w-full max-w-7xl px-4 py-4 md:px-8 md:py-8">
            <Outlet />
          </div>
        )}
      </main>
    </div>
  )
}
