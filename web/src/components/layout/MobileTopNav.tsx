import { CalendarDays, Home, Layers, Menu, MessageSquare } from 'lucide-react'
import type { ComponentType } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

type NavItem = {
  path: string
  label: string
  icon: ComponentType<{ className?: string }>
}

const PRIMARY_ITEMS: NavItem[] = [
  { path: '/dashboard', label: 'Hoje', icon: Home },
  { path: '/chat', label: 'Chat', icon: MessageSquare },
  { path: '/flashcards', label: 'Cards', icon: Layers },
  { path: '/schedule', label: 'Calendário', icon: CalendarDays },
  { path: '/more', label: 'Menu', icon: Menu },
]

const CALENDAR_ROUTES = new Set(['/studyplan', '/schedule', '/tasks'])

function isActive(path: string, pathname: string) {
  if (path === '/schedule') return CALENDAR_ROUTES.has(pathname)
  return pathname === path
}

export function MobileTopNav() {
  const navigate = useNavigate()
  const { pathname } = useLocation()

  return (
    <nav
      aria-label="Navegação principal"
      className="sticky top-14 z-20 grid grid-cols-5 gap-1 border-b app-divider bg-transparent px-2 pb-2 pt-1 md:hidden"
    >
      {PRIMARY_ITEMS.map(({ path, label, icon: Icon }) => {
        const active = isActive(path, pathname)
        return (
          <button
            key={path}
            type="button"
            onClick={() => navigate(path)}
            className="inline-flex min-w-0 items-center justify-center gap-1 rounded-full px-1.5 py-1.5 text-[11px] font-semibold transition-colors"
            style={{
              backgroundColor: active ? 'var(--ui-accent)' : 'var(--ui-surface-2)',
              color: active ? 'var(--ui-bg)' : 'var(--ui-text-dim)',
            }}
          >
            <Icon className="h-3 w-3 shrink-0" />
            <span className="truncate">{label}</span>
          </button>
        )
      })}
    </nav>
  )
}
