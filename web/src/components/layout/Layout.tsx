import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'

// These routes use a full-height layout without inner padding/max-width
const FULL_HEIGHT_ROUTES = ['/chat', '/schedule']

export function Layout() {
  const { pathname } = useLocation()
  const isFullHeight = FULL_HEIGHT_ROUTES.includes(pathname)

  return (
    <div className="flex min-h-screen bg-zinc-950 text-zinc-100">
      <Sidebar />
      <main className="flex flex-1 flex-col pl-64 overflow-hidden">
        {isFullHeight ? (
          <Outlet />
        ) : (
          <div className="mx-auto w-full max-w-6xl px-8 py-8">
            <Outlet />
          </div>
        )}
      </main>
    </div>
  )
}
