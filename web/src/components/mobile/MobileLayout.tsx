import { useState, type CSSProperties } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  CalendarDays,
  ChevronLeft,
  Flame,
  Home,
  Layers,
  Menu,
  MessageSquare,
  Plus,
  Search,
  Sun,
  Moon,
} from 'lucide-react'
import { useAppTheme } from '@/context/ThemeContext'
import { apiClient } from '@/api/client'

// ── Tab config ───────────────────────────────────────────────────────────────
const PRIMARY_TABS = [
  { path: '/dashboard',   label: 'Hoje',       Icon: Home },
  { path: '/chat',        label: 'Chat',       Icon: MessageSquare },
  { path: '/flashcards',  label: 'Cards',      Icon: Layers },
  { path: '/studyplan',   label: 'Calendário', Icon: CalendarDays },
  { path: '/more',        label: 'Menu',       Icon: Menu },
]

// Paths that count as "Calendário" tab active
const CALENDARIO_PATHS = ['/studyplan', '/schedule', '/tasks']

// ── FAB config per route ─────────────────────────────────────────────────────
// ── Mobile header ─────────────────────────────────────────────────────────────
const ROUTE_TITLES: Record<string, string> = {
  '/dashboard':  'Hoje',
  '/chat':       'Chat',
  '/flashcards': 'Flashcards',
  '/studyplan':  'Calendário',
  '/schedule':   'Calendário',
  '/tasks':      'Calendário',
  '/more':       'Menu',
  '/kanban':     'Leituras',
  '/ingest':     'Inserir',
  '/notes':      'Notas',
  '/artifacts':  'Artefatos',
  '/docs':       'Documentos',
  '/settings':   'Preferências',
}

const PRIMARY_PATHS = new Set(PRIMARY_TABS.map(t => t.path))

// ── Component ─────────────────────────────────────────────────────────────────
export function MobileLayout({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const { theme, toggleTheme } = useAppTheme()

  const [fabOpen, setFabOpen] = useState(false)
  const [routineOpen, setRoutineOpen] = useState(false)

  const title = ROUTE_TITLES[pathname] ?? 'DocOps'
  const isPrimary = PRIMARY_PATHS.has(pathname) || CALENDARIO_PATHS.includes(pathname)
  const isSecondary = !isPrimary

  function activeFor(tabPath: string) {
    if (tabPath === '/studyplan') return CALENDARIO_PATHS.includes(pathname) || pathname === '/studyplan'
    return pathname === tabPath
  }

  const bg = 'var(--ui-bg)'
  const surface1 = 'var(--ui-surface-1)'
  const borderSoft = 'var(--ui-border-soft)'
  const accent = 'var(--ui-accent)'
  const text = 'var(--ui-text)'
  const textDim = 'var(--ui-text-dim)'

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        display: 'flex',
        flexDirection: 'column',
        background: bg,
        fontFamily: "'Manrope', 'Segoe UI', system-ui, sans-serif",
        overscrollBehavior: 'none',
        WebkitOverflowScrolling: 'touch' as any,
      }}
    >
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header
        style={{
          position: 'relative',
          zIndex: 20,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '12px 16px 10px',
          paddingTop: 'max(12px, env(safe-area-inset-top, 12px))',
          background: `${bg}f5`,
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
          borderBottom: `1px solid ${borderSoft}`,
          flexShrink: 0,
        }}
      >
        {isSecondary && (
          <button
            onClick={() => navigate(-1)}
            aria-label="Voltar"
            style={{
              width: 34,
              height: 34,
              borderRadius: 999,
              background: surface1,
              border: `1px solid ${borderSoft}`,
              color: textDim,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <ChevronLeft size={16} />
          </button>
        )}

        <span
          style={{
            flex: 1,
            fontSize: 17,
            fontWeight: 800,
            color: text,
            letterSpacing: '-0.02em',
          }}
        >
          {title}
        </span>

        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          aria-label="Alternar tema"
          style={{
            width: 34,
            height: 34,
            borderRadius: 999,
            background: surface1,
            border: `1px solid ${borderSoft}`,
            color: textDim,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
        </button>

        {/* Search */}
        <button
          aria-label="Buscar"
          style={{
            width: 34,
            height: 34,
            borderRadius: 999,
            background: surface1,
            border: `1px solid ${borderSoft}`,
            color: textDim,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Search size={15} />
        </button>

        {/* Chat shortcut (visible when not on /chat) */}
        {pathname !== '/chat' && (
          <button
            onClick={() => navigate('/chat')}
            aria-label="Chat"
            style={{
              width: 34,
              height: 34,
              borderRadius: 999,
              background: `color-mix(in srgb, ${accent} 15%, transparent)`,
              border: `1px solid color-mix(in srgb, ${accent} 40%, transparent)`,
              color: accent,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <MessageSquare size={15} />
          </button>
        )}
      </header>

      {/* ── Top tab nav ───────────────────────────────────────────────────── */}
      <nav
        aria-label="Navegação principal"
        style={{
          position: 'relative',
          zIndex: 20,
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          padding: '6px 12px 8px',
          overflowX: 'auto',
          scrollbarWidth: 'none',
          background: `${bg}f5`,
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
          borderBottom: `1px solid ${borderSoft}`,
          flexShrink: 0,
          WebkitOverflowScrolling: 'touch' as any,
        }}
      >
        {PRIMARY_TABS.map(({ path, label, Icon }) => {
          const active = activeFor(path)
          return (
            <button
              key={path}
              onClick={() => navigate(path)}
              aria-label={label}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '6px 12px',
                borderRadius: 999,
                border: 'none',
                background: active
                  ? accent
                  : `color-mix(in srgb, ${surface1} 80%, transparent)`,
                color: active ? 'var(--ui-bg)' : textDim,
                fontSize: 12,
                fontWeight: active ? 700 : 500,
                letterSpacing: '-0.01em',
                cursor: 'pointer',
                flexShrink: 0,
                transition: 'background .15s, color .15s',
                whiteSpace: 'nowrap',
              }}
            >
              <Icon size={13} strokeWidth={active ? 2.4 : 1.8} />
              {label}
            </button>
          )
        })}
      </nav>

      {/* ── Main content ──────────────────────────────────────────────────── */}
      <main
        style={{
          flex: 1,
          overflowY: 'auto',
          overflowX: 'hidden',
          position: 'relative',
          zIndex: 5,
        }}
      >
        {children}
      </main>

      {/* ── FAB ───────────────────────────────────────────────────────────── */}
      <FabButton
        pathname={pathname}
        navigate={navigate}
        fabOpen={fabOpen}
        setFabOpen={setFabOpen}
        setRoutineOpen={setRoutineOpen}
      />

      {/* ── Routine popup ─────────────────────────────────────────────────── */}
      {routineOpen && (
        <RoutinePopup onClose={() => setRoutineOpen(false)} />
      )}
    </div>
  )
}

// ── FAB ──────────────────────────────────────────────────────────────────────
function FabButton({
  pathname,
  navigate,
  fabOpen,
  setFabOpen,
  setRoutineOpen,
}: {
  pathname: string
  navigate: (to: string) => void
  fabOpen: boolean
  setFabOpen: (v: boolean) => void
  setRoutineOpen: (v: boolean) => void
}) {
  const accent = 'var(--ui-accent)'
  const bg = 'var(--ui-bg)'

  type FabEntry = {
    icon: React.ReactNode
    label: string
    action: () => void
    tone?: 'accent' | 'default'
  }

  const fabMap: Record<string, FabEntry[]> = {
    '/dashboard': [
      { icon: <Plus size={17} />, label: 'Inserir documento', action: () => navigate('/ingest'), tone: 'accent' },
    ],
    '/flashcards': [
      { icon: <Plus size={17} />, label: 'Novo deck', action: () => {}, tone: 'accent' },
    ],
    '/studyplan': [
      { icon: <Plus size={17} />, label: 'Nova tarefa', action: () => { setFabOpen(false); navigate('/studyplan?new=1') }, tone: 'accent' },
      { icon: <Flame size={15} />, label: 'Modificar rotina', action: () => { setFabOpen(false); setRoutineOpen(true) } },
    ],
    '/schedule': [
      { icon: <Plus size={17} />, label: 'Nova tarefa', action: () => { setFabOpen(false); navigate('/studyplan?new=1') }, tone: 'accent' },
      { icon: <Flame size={15} />, label: 'Modificar rotina', action: () => { setFabOpen(false); setRoutineOpen(true) } },
    ],
    '/kanban': [
      { icon: <Plus size={17} />, label: 'Adicionar leitura', action: () => {}, tone: 'accent' },
    ],
    '/notes': [
      { icon: <Plus size={17} />, label: 'Nova nota', action: () => {}, tone: 'accent' },
    ],
    '/artifacts': [
      { icon: <Plus size={17} />, label: 'Novo artefato', action: () => {}, tone: 'accent' },
    ],
  }

  const entries = fabMap[pathname]
  if (!entries) return null

  const hasMultiple = entries.length > 1

  if (!hasMultiple) {
    const e = entries[0]
    return (
      <button
        onClick={e.action}
        aria-label={e.label}
        style={{
          position: 'absolute',
          bottom: 'max(20px, env(safe-area-inset-bottom, 20px))',
          right: 18,
          zIndex: 25,
          width: 52,
          height: 52,
          borderRadius: 999,
          background: accent,
          color: bg,
          border: 'none',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 4px 20px rgba(0,0,0,0.28)',
          cursor: 'pointer',
        }}
      >
        <Plus size={22} />
      </button>
    )
  }

  // Multi-action FAB
  return (
    <>
      {fabOpen && (
        <div
          onClick={() => setFabOpen(false)}
          style={{ position: 'fixed', inset: 0, zIndex: 24 }}
        />
      )}
      {fabOpen && (
        <div
          style={{
            position: 'absolute',
            bottom: 'calc(max(20px, env(safe-area-inset-bottom, 20px)) + 60px)',
            right: 18,
            zIndex: 26,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-end',
            gap: 10,
          }}
        >
          {entries.map((e, i) => (
            <button
              key={i}
              onClick={() => { e.action(); setFabOpen(false) }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                background: 'var(--ui-surface-1)',
                border: '1px solid var(--ui-border-soft)',
                borderRadius: 12,
                padding: '10px 14px',
                color: e.tone === 'accent' ? accent : 'var(--ui-text)',
                fontSize: 13,
                fontWeight: 700,
                cursor: 'pointer',
                boxShadow: '0 4px 14px rgba(0,0,0,0.22)',
                whiteSpace: 'nowrap',
              }}
            >
              {e.icon}
              {e.label}
            </button>
          ))}
        </div>
      )}
      <button
        onClick={() => setFabOpen(!fabOpen)}
        aria-label="Ações"
        style={{
          position: 'absolute',
          bottom: 'max(20px, env(safe-area-inset-bottom, 20px))',
          right: 18,
          zIndex: 25,
          width: 52,
          height: 52,
          borderRadius: 999,
          background: accent,
          color: bg,
          border: 'none',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 4px 20px rgba(0,0,0,0.28)',
          cursor: 'pointer',
          transform: fabOpen ? 'rotate(45deg)' : 'rotate(0deg)',
          transition: 'transform .2s ease',
        }}
      >
        <Plus size={22} />
      </button>
    </>
  )
}

// ── Routine Popup ─────────────────────────────────────────────────────────────
const DAYS_LABELS = ['Seg','Ter','Qua','Qui','Sex','Sáb','Dom']

function RoutinePopup({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [what, setWhat] = useState('')
  const [startTime, setStartTime] = useState('08:00')
  const [endTime, setEndTime] = useState('09:00')
  // selected days: 0=Mon...6=Sun
  const [selectedDays, setSelectedDays] = useState<Set<number>>(new Set([0,1,2,3]))

  const surface1 = 'var(--ui-surface-1)'
  const borderSoft = 'var(--ui-border-soft)'
  const accent = 'var(--ui-accent)'
  const accentSoft = 'var(--ui-accent-soft)'
  const text = 'var(--ui-text)'
  const textDim = 'var(--ui-text-dim)'
  const textMeta = 'var(--ui-text-meta)'
  const s2 = 'var(--ui-surface-2)'
  const s3 = 'var(--ui-surface-3)'

  const saveMut = useMutation({
    mutationFn: async () => {
      const days = Array.from(selectedDays)
      await Promise.all(days.map(day =>
        apiClient.createSchedule({
          title: what.trim(),
          day_of_week: day,
          start_time: startTime,
          end_time: endTime,
          note: null,
          active: true,
        })
      ))
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['calendar-schedules'] })
      qc.invalidateQueries({ queryKey: ['calendar-overview'] })
      toast.success(`Rotina salva para ${selectedDays.size} dia(s)`)
      onClose()
    },
    onError: () => toast.error('Erro ao salvar rotina'),
  })

  function toggleDay(d: number) {
    setSelectedDays(prev => {
      const next = new Set(prev)
      if (next.has(d)) {
        next.delete(d)
      } else {
        next.add(d)
      }
      return next
    })
  }

  const canSave = what.trim() && startTime && endTime && selectedDays.size > 0

  const inputStyle: CSSProperties = {
    width: '100%',
    height: 42,
    background: s2,
    border: `1px solid ${borderSoft}`,
    borderRadius: 10,
    padding: '0 12px',
    fontSize: 14,
    color: text,
    fontFamily: 'inherit',
    outline: 'none',
    boxSizing: 'border-box',
  }

  const labelStyle: CSSProperties = {
    fontSize: 10,
    color: textMeta,
    fontFamily: "'IBM Plex Mono', monospace",
    letterSpacing: '0.12em',
    textTransform: 'uppercase' as const,
    display: 'block',
    marginBottom: 6,
  }

  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 40, animation: 'fadeIn .15s ease' }} />

      <div style={{ position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 41, background: surface1, borderRadius: '20px 20px 0 0', padding: '20px 20px calc(20px + env(safe-area-inset-bottom, 0px))', animation: 'slideUp .22s ease-out', maxHeight: '90vh', overflowY: 'auto' }}>
        <div style={{ width: 36, height: 4, borderRadius: 2, background: borderSoft, margin: '0 auto 18px' }} />

        <div style={{ fontSize: 10, fontFamily: "'IBM Plex Mono', monospace", letterSpacing: '0.16em', textTransform: 'uppercase', color: textMeta, marginBottom: 4 }}>
          Modificar rotina
        </div>
        <h3 style={{ fontSize: 18, fontWeight: 800, color: text, margin: '0 0 18px', letterSpacing: '-0.02em' }}>
          Adicionar bloco semanal
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Activity name */}
          <div>
            <label style={labelStyle}>Atividade</label>
            <input autoFocus value={what} onChange={e => setWhat(e.target.value)} placeholder="Ex: Revisão — Cálculo I" style={inputStyle} />
          </div>

          {/* Time range */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label style={labelStyle}>Início</label>
              <input type="time" value={startTime} onChange={e => setStartTime(e.target.value)} style={{ ...inputStyle, colorScheme: 'dark' }} />
            </div>
            <div>
              <label style={labelStyle}>Fim</label>
              <input type="time" value={endTime} onChange={e => setEndTime(e.target.value)} style={{ ...inputStyle, colorScheme: 'dark' }} />
            </div>
          </div>

          {/* Day picker */}
          <div>
            <label style={labelStyle}>Dias da semana</label>
            <div style={{ display: 'flex', gap: 6 }}>
              {DAYS_LABELS.map((label, i) => {
                const active = selectedDays.has(i)
                return (
                  <button
                    key={i}
                    onClick={() => toggleDay(i)}
                    style={{
                      flex: 1, height: 36, borderRadius: 8, border: `1px solid ${active ? accent : borderSoft}`,
                      background: active ? accentSoft : s2,
                      color: active ? accent : textMeta,
                      fontSize: 11, fontWeight: active ? 700 : 500,
                      cursor: 'pointer', transition: 'all .15s',
                      padding: 0,
                    }}
                  >
                    {label.slice(0,1)}
                  </button>
                )
              })}
            </div>
            <div style={{ fontSize: 11, color: textMeta, marginTop: 6 }}>
              {selectedDays.size === 0
                ? 'Nenhum dia selecionado'
                : Array.from(selectedDays).sort().map(d => DAYS_LABELS[d]).join(', ')}
            </div>
          </div>

          {/* Save button */}
          <button
            onClick={() => { if (canSave) saveMut.mutate() }}
            disabled={!canSave || saveMut.isPending}
            style={{
              width: '100%', height: 46, borderRadius: 12,
              background: canSave ? accent : s3,
              color: canSave ? 'var(--ui-bg)' : textDim,
              border: 'none', fontSize: 14, fontWeight: 700,
              cursor: canSave ? 'pointer' : 'not-allowed',
              transition: 'background .2s', marginTop: 4,
            }}
          >
            {saveMut.isPending ? 'Salvando...' : `Salvar rotina ${selectedDays.size > 0 ? `(${selectedDays.size} dia${selectedDays.size > 1 ? 's' : ''})` : ''}`}
          </button>
        </div>
      </div>

      <style>{`
        @keyframes fadeIn { from { opacity: 0 } to { opacity: 1 } }
        @keyframes slideUp { from { transform: translateY(100%) } to { transform: translateY(0) } }
      `}</style>
    </>
  )
}
