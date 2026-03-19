import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Menu } from 'lucide-react'
import { Sidebar } from './Sidebar'

// These routes use a full-height layout without inner padding/max-width
const FULL_HEIGHT_ROUTES = ['/chat', '/schedule', '/notes']

export function Layout() {
  const { pathname } = useLocation()
  const isFullHeight = FULL_HEIGHT_ROUTES.includes(pathname)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)

  useEffect(() => {
    document.body.style.overflow = mobileSidebarOpen ? 'hidden' : ''
    return () => {
      document.body.style.overflow = ''
    }
  }, [mobileSidebarOpen])

  return (
    <div className="flex min-h-screen bg-zinc-950 text-zinc-100">
      <Sidebar
        mobileOpen={mobileSidebarOpen}
        onMobileClose={() => setMobileSidebarOpen(false)}
      />

      <main className="flex flex-1 flex-col overflow-hidden md:pl-64">
        <header className="sticky top-0 z-30 flex h-14 items-center border-b border-zinc-800 bg-zinc-950/95 px-4 backdrop-blur md:hidden">
          <button
            type="button"
            aria-label="Abrir menu"
            className="inline-flex h-9 w-9 items-center justify-center rounded-md text-zinc-200 transition-colors hover:bg-zinc-800"
            onClick={() => setMobileSidebarOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </button>
          <span className="ml-3 text-sm font-semibold text-zinc-100">DocOps Agent</span>
        </header>

        {isFullHeight ? (
          <Outlet />
        ) : (
          <div className="mx-auto w-full max-w-6xl px-4 py-4 md:px-8 md:py-8">
            <Outlet />
          </div>
        )}
      </main>
    </div>
  )
}
