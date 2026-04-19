import { NavLink } from 'react-router-dom'
import {
  CalendarDays,
  FileText,
  KanbanSquare,
  Layers,
  LogOut,
  Settings2,
  StickyNote,
  Upload,
  CheckSquare,
} from 'lucide-react'
import { useAuth } from '@/auth/AuthProvider'
import { cn } from '@/lib/utils'

const MENU_LINKS = [
  { to: '/docs', label: 'Documentos', sub: 'Todos os arquivos indexados', icon: FileText },
  { to: '/ingest', label: 'Inserção', sub: 'Upload e importação de conteúdo', icon: Upload },
  { to: '/notes', label: 'Notas', sub: 'Anotações vinculadas aos documentos', icon: StickyNote },
  { to: '/tasks', label: 'Tarefas', sub: 'Sua fila de execução diária', icon: CheckSquare },
  { to: '/studyplan', label: 'Plano de Estudo', sub: 'Rotina, metas e tarefas', icon: CalendarDays },
  { to: '/artifacts', label: 'Artefatos', sub: 'Resumos, mapas, quizzes e mais', icon: Layers },
  { to: '/kanban', label: 'Kanban de Leitura', sub: 'Organize seu progresso de leitura', icon: KanbanSquare },
  { to: '/settings', label: 'Configurações', sub: 'Conta, IA e preferências', icon: Settings2 },
] as const

export function MobileMenu() {
  const { user, logout } = useAuth()

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 px-0 py-1 md:gap-6 md:py-2">
      <section className="app-surface p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-[color:var(--ui-accent)] text-base font-bold text-[color:var(--ui-bg)]">
            {user?.name?.[0]?.toUpperCase() ?? user?.email?.[0]?.toUpperCase() ?? 'U'}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-[color:var(--ui-text)]">
              {user?.name ?? 'Usuário'}
            </p>
            <p className="truncate text-xs text-[color:var(--ui-text-meta)]">{user?.email ?? ''}</p>
          </div>
        </div>
      </section>

      <section className="app-surface overflow-hidden">
        {MENU_LINKS.map(({ to, label, sub, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 border-b app-divider px-4 py-3 transition-colors last:border-b-0',
                isActive
                  ? 'bg-[color:var(--ui-surface-2)] text-[color:var(--ui-accent)]'
                  : 'text-[color:var(--ui-text-dim)] hover:bg-[color:var(--ui-surface-2)] hover:text-[color:var(--ui-text)]',
              )
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold">{label}</p>
              <p className="truncate text-xs text-[color:var(--ui-text-meta)]">{sub}</p>
            </div>
          </NavLink>
        ))}
      </section>

      <section className="w-full px-0 pt-1">
        <button
          type="button"
          onClick={logout}
          className="flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-[color:var(--ui-border-soft)] px-4 text-sm font-medium text-[color:var(--ui-text-meta)] transition-colors hover:border-[#944747] hover:bg-[#8f3f3f]/10 hover:text-[#efb0b0]"
        >
          <LogOut className="h-4 w-4" />
          Sair
        </button>
      </section>

      <p className="text-center font-meta text-[10px] text-[color:var(--ui-text-meta)]">
        DocOps Agent · menu
      </p>
    </div>
  )
}
