import { useEffect, useRef, useState } from 'react'
import { NavLink } from 'react-router-dom'
import {
  Archive,
  CalendarDays,
  FileText,
  GraduationCap,
  KanbanSquare,
  Layers,
  LayoutDashboard,
  ListTodo,
  LogOut,
  MessageSquare,
  Plus,
  Settings2,
  StickyNote,
  Upload,
  X,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useAuth } from '@/auth/AuthProvider'
import { apiClient, type CalendarOverview } from '@/api/client'
import { FocusTimer, FocusTimerTrigger } from '@/components/FocusTimer'

type SidebarProps = {
  mobileOpen: boolean
  isDesktop: boolean
  onMobileClose: () => void
}

export function Sidebar({ mobileOpen, isDesktop, onMobileClose }: SidebarProps) {
  const { user, logout } = useAuth()
  const [focusOpen, setFocusOpen] = useState(false)
  const sidebarRef = useRef<HTMLElement | null>(null)

  const { data: calendarOverview } = useQuery<CalendarOverview>({
    queryKey: ['calendar-overview', 'today'],
    queryFn: () => apiClient.getCalendarOverview(),
    refetchInterval: 5 * 60 * 1000,
    retry: 1,
  })

  const todayReminders = calendarOverview?.today_reminders.length ?? 0
  const isMobileClosed = !mobileOpen && !isDesktop

  useEffect(() => {
    const sidebar = sidebarRef.current
    if (!sidebar) return
    ;(sidebar as HTMLElement & { inert?: boolean }).inert = isMobileClosed
    return () => {
      ;(sidebar as HTMLElement & { inert?: boolean }).inert = false
    }
  }, [isMobileClosed])

  const links = [
    { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, end: true, badge: null },
    { to: '/chat', label: 'Chat', icon: MessageSquare, end: false, badge: null },
    { to: '/schedule', label: 'Calendário', icon: CalendarDays, end: false, badge: todayReminders > 0 ? todayReminders : null },
    { to: '/docs', label: 'Documentos', icon: FileText, end: false, badge: null },
    { to: '/ingest', label: 'Inserção', icon: Upload, end: false, badge: null },
    { to: '/notes', label: 'Notas', icon: StickyNote, end: false, badge: null },
    { to: '/tasks', label: 'Tarefas', icon: ListTodo, end: false, badge: null },
    { to: '/flashcards', label: 'Flashcards', icon: Layers, end: false, badge: null },
    { to: '/studyplan', label: 'Plano de Estudos', icon: GraduationCap, end: false, badge: null },
    { to: '/settings', label: 'Configurações', icon: Settings2, end: false, badge: null },
    { to: '/kanban', label: 'Kanban de Leitura', icon: KanbanSquare, end: false, badge: null },
    { to: '/artifacts', label: 'Artefatos', icon: Archive, end: false, badge: null },
  ]

  return (
    <>
      <aside
        ref={sidebarRef}
        id="app-sidebar"
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r app-divider bg-[color:var(--ui-bg)]/96 px-4 py-6 backdrop-blur transition-transform duration-200',
          mobileOpen || isDesktop ? 'pointer-events-auto' : 'pointer-events-none',
          mobileOpen ? 'translate-x-0' : '-translate-x-full',
          'md:translate-x-0'
        )}
        aria-hidden={isMobileClosed ? true : undefined}
      >
        <div className="mb-6 flex items-start gap-3 px-2">
          <div className="min-w-0">
            <p className="font-headline text-2xl font-bold tracking-tight text-[color:var(--ui-accent)]">DocOps Agent</p>
          </div>

          <button
            type="button"
            aria-label="Fechar menu"
            className="ml-auto inline-flex h-8 w-8 items-center justify-center rounded-lg border border-transparent text-[color:var(--ui-text-meta)] transition-colors hover:border-[color:var(--ui-border)] hover:bg-[color:var(--ui-surface-1)] hover:text-[color:var(--ui-text)] md:hidden"
            onClick={onMobileClose}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-1 py-2">
          {links.map(({ to, label, icon: Icon, end, badge }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-lg border border-transparent px-3 py-2.5 text-sm font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--ui-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[color:var(--ui-bg)]',
                  isActive
                    ? 'border-r-2 border-r-[color:var(--ui-accent)] bg-[color:var(--ui-surface-2)] font-bold text-[color:var(--ui-accent)]'
                    : 'text-[color:var(--ui-text-dim)] hover:bg-[color:var(--ui-surface-2)] hover:text-[color:var(--ui-text)]'
                )
              }
              onClick={onMobileClose}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="flex-1">{label}</span>
              {badge !== null && (
                <span className="flex h-4 min-w-4 items-center justify-center rounded-full border border-[color:var(--ui-border-strong)] bg-[color:var(--ui-accent)] px-1 text-[10px] font-bold text-white">
                  {badge}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="space-y-2 border-t app-divider px-2 pt-4">
          <Button
            asChild
            size="sm"
            className="h-10 w-full justify-center gap-1.5 rounded-lg border border-[color:var(--ui-accent)] bg-[color:var(--ui-accent)] text-[color:var(--ui-bg)] hover:bg-[color:var(--ui-accent-strong)]"
          >
            <NavLink to="/artifacts" onClick={onMobileClose}>
              <Plus className="h-3.5 w-3.5" />
              Novo artefato
            </NavLink>
          </Button>

          {user && (
            <div className="mb-2 min-w-0 px-1">
              <p className="truncate text-xs font-medium text-[color:var(--ui-text-dim)]">{user.name}</p>
              <p className="truncate text-xs text-[color:var(--ui-text-meta)]">{user.email}</p>
            </div>
          )}

          <FocusTimerTrigger onClick={() => setFocusOpen(true)} />

          <button
            onClick={logout}
            className="flex w-full items-center gap-2 rounded-lg border border-transparent px-3 py-2 text-xs font-medium text-[color:var(--ui-text-meta)] transition-colors hover:border-[#944747] hover:bg-[#8f3f3f]/15 hover:text-[#efb0b0]"
          >
            <LogOut className="h-3.5 w-3.5 shrink-0" />
            Sair
          </button>

        </div>
      </aside>

      {mobileOpen && (
        <button
          type="button"
          aria-label="Fechar menu"
          className="fixed inset-0 z-30 bg-[color:var(--ui-bg)]/72 md:hidden"
          onClick={onMobileClose}
        />
      )}

      {focusOpen && <FocusTimer onClose={() => setFocusOpen(false)} />}
    </>
  )
}
