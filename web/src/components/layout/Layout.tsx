import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Menu } from 'lucide-react'
import { Sidebar } from './Sidebar'

// These routes use a full-height layout without inner padding/max-width
const FULL_HEIGHT_ROUTES = ['/chat', '/schedule', '/notes']
const DESKTOP_MEDIA_QUERY = '(min-width: 768px)'

type BodyScrollLockState = {
  count: number
  overflow: string
}

type ScrollLockWindow = Window & {
  __docopsBodyScrollLockState?: BodyScrollLockState
}

function acquireBodyScrollLock() {
  const scrollLockWindow = window as ScrollLockWindow
  const state = scrollLockWindow.__docopsBodyScrollLockState ??= {
    count: 0,
    overflow: '',
  }

  if (state.count === 0) {
    state.overflow = document.body.style.overflow
  }

  state.count += 1
  document.body.style.overflow = 'hidden'

  return () => {
    const currentState = scrollLockWindow.__docopsBodyScrollLockState

    if (!currentState) return

    currentState.count = Math.max(0, currentState.count - 1)

    if (currentState.count === 0) {
      document.body.style.overflow = currentState.overflow
      currentState.overflow = ''
    }
  }
}

export function Layout() {
  const { pathname } = useLocation()
  const isFullHeight = FULL_HEIGHT_ROUTES.includes(pathname)
  const [isDesktop, setIsDesktop] = useState(() =>
    typeof window !== 'undefined'
      ? window.matchMedia(DESKTOP_MEDIA_QUERY).matches
      : false,
  )
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)

  useEffect(() => {
    const mediaQuery = window.matchMedia(DESKTOP_MEDIA_QUERY)
    const legacyMediaQuery = mediaQuery as MediaQueryList & {
      addListener: (listener: (event: MediaQueryListEvent) => void) => void
      removeListener: (listener: (event: MediaQueryListEvent) => void) => void
    }

    const handleChange = (event: MediaQueryListEvent) => {
      setIsDesktop(event.matches)

      if (event.matches) {
        setMobileSidebarOpen(false)
      }
    }

    setIsDesktop(mediaQuery.matches)

    if (mediaQuery.matches) {
      setMobileSidebarOpen(false)
    }

    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', handleChange)
      return () => mediaQuery.removeEventListener('change', handleChange)
    }

    legacyMediaQuery.addListener(handleChange)
    return () => legacyMediaQuery.removeListener(handleChange)
  }, [])

  useEffect(() => {
    setMobileSidebarOpen(false)
  }, [pathname])

  useEffect(() => {
    const handleOrientationChange = () => {
      setMobileSidebarOpen(false)
    }

    window.addEventListener('orientationchange', handleOrientationChange)
    return () => window.removeEventListener('orientationchange', handleOrientationChange)
  }, [])

  useEffect(() => {
    if (!mobileSidebarOpen || isDesktop) return
    return acquireBodyScrollLock()
  }, [mobileSidebarOpen, isDesktop])

  useEffect(() => {
    if (!mobileSidebarOpen) return

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMobileSidebarOpen(false)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [mobileSidebarOpen])

  return (
    <div className="app-editorial flex min-h-screen text-[color:var(--ui-text)]">
      <Sidebar
        mobileOpen={mobileSidebarOpen}
        isDesktop={isDesktop}
        onMobileClose={() => setMobileSidebarOpen(false)}
      />

      <main className="relative z-10 flex flex-1 flex-col overflow-hidden md:pl-64">
        <header className="sticky top-0 z-20 flex h-14 items-center border-b px-4 md:hidden app-divider bg-[color:var(--ui-bg)]/95 backdrop-blur">
          <button
            type="button"
            aria-label="Abrir menu"
            aria-controls="app-sidebar"
            aria-expanded={mobileSidebarOpen}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-transparent text-[color:var(--ui-text-dim)] transition-colors hover:border-[color:var(--ui-border)] hover:bg-[color:var(--ui-surface-1)] hover:text-[color:var(--ui-text)]"
            onClick={() => setMobileSidebarOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </button>
          <span className="ml-3 text-sm font-semibold text-[color:var(--ui-text)]">DocOps Agent</span>
        </header>

        {isFullHeight ? (
          <Outlet />
        ) : (
          <div className="relative z-10 mx-auto w-full max-w-7xl px-4 py-4 md:px-8 md:py-8">
            <Outlet />
          </div>
        )}
      </main>
    </div>
  )
}
