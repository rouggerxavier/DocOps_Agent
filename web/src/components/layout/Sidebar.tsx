import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Upload,
  MessageSquare,
  FileText,
  Archive,
  CalendarDays,
  BookOpen,
  LogOut,
  StickyNote,
  ListTodo,
  Layers,
  GraduationCap,
  KanbanSquare,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import { useAuth } from '@/auth/AuthProvider'
import { apiClient, type CalendarOverview } from '@/api/client'
import { FocusTimer, FocusTimerTrigger } from '@/components/FocusTimer'

export function Sidebar() {
  const { user, logout } = useAuth()
  const [focusOpen, setFocusOpen] = useState(false)

  const { data: calendarOverview } = useQuery<CalendarOverview>({
    queryKey: ['calendar-overview', 'today'],
    queryFn: () => apiClient.getCalendarOverview(),
    refetchInterval: 5 * 60 * 1000, // refetch every 5 min
    retry: 1,
  })

  const todayReminders = calendarOverview?.today_reminders.length ?? 0

  const links = [
    { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true, badge: null },
    { to: '/chat', label: 'Chat', icon: MessageSquare, end: false, badge: null },
    { to: '/schedule', label: 'Calendário', icon: CalendarDays, end: false, badge: todayReminders > 0 ? todayReminders : null },
    { to: '/docs', label: 'Documentos', icon: FileText, end: false, badge: null },
    { to: '/ingest', label: 'Inserção', icon: Upload, end: false, badge: null },
    { to: '/notes', label: 'Notas', icon: StickyNote, end: false, badge: null },
    { to: '/tasks', label: 'Tarefas', icon: ListTodo, end: false, badge: null },
    { to: '/flashcards', label: 'Flashcards', icon: Layers, end: false, badge: null },
    { to: '/studyplan', label: 'Plano de Estudos', icon: GraduationCap, end: false, badge: null },
    { to: '/kanban', label: 'Kanban de Leitura', icon: KanbanSquare, end: false, badge: null },
    { to: '/artifacts', label: 'Artefatos', icon: Archive, end: false, badge: null },
  ]

  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-zinc-800 bg-zinc-950">
        {/* Logo */}
        <div className="flex h-16 items-center gap-3 border-b border-zinc-800 px-6">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600">
            <BookOpen className="h-4 w-4 text-white" />
          </div>
          <div>
            <p className="text-sm font-semibold text-zinc-100">DocOps Agent</p>
            <p className="text-xs text-zinc-500">RAG Local</p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
          {links.map(({ to, label, icon: Icon, end, badge }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-blue-600/20 text-blue-400'
                    : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100'
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="flex-1">{label}</span>
              {badge !== null && (
                <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-blue-600 px-1 text-[10px] font-bold text-white">
                  {badge}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="border-t border-zinc-800 px-4 py-4 space-y-1">
          {user && (
            <div className="min-w-0 px-1 mb-2">
              <p className="truncate text-xs font-medium text-zinc-300">{user.name}</p>
              <p className="truncate text-xs text-zinc-600">{user.email}</p>
            </div>
          )}
          <FocusTimerTrigger onClick={() => setFocusOpen(true)} />
          <button
            onClick={logout}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-red-400"
          >
            <LogOut className="h-3.5 w-3.5 shrink-0" />
            Sair
          </button>
          <p className="px-1 text-xs text-zinc-700">v0.1.0 · Gemini + Chroma</p>
        </div>
      </aside>

      {focusOpen && <FocusTimer onClose={() => setFocusOpen(false)} />}
    </>
  )
}
