import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Upload,
  MessageSquare,
  FileText,
  Archive,
  BookOpen,
  LogOut,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/auth/AuthProvider'

const links = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/ingest', label: 'Ingestão', icon: Upload, end: false },
  { to: '/chat', label: 'Chat', icon: MessageSquare, end: false },
  { to: '/docs', label: 'Documentos', icon: FileText, end: false },
  { to: '/artifacts', label: 'Artefatos', icon: Archive, end: false },
]

export function Sidebar() {
  const { user, logout } = useAuth()

  return (
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
      <nav className="flex-1 space-y-1 px-3 py-4">
        {links.map(({ to, label, icon: Icon, end }) => (
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
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer: usuário logado + botão sair */}
      <div className="border-t border-zinc-800 px-4 py-4 space-y-3">
        {user && (
          <div className="min-w-0 px-1">
            <p className="truncate text-xs font-medium text-zinc-300">{user.name}</p>
            <p className="truncate text-xs text-zinc-600">{user.email}</p>
          </div>
        )}
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
  )
}
