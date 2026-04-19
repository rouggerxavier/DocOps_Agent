import { type CSSProperties, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import {
  AlertTriangle,
  Bell,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Circle,
  Clock,
  Plus,
  Trash2,
} from 'lucide-react'
import {
  apiClient,
  type ReminderItem,
  type ScheduleItem,
  type StudyPlanItem,
  type TaskItem,
} from '@/api/client'

// ── Tokens ────────────────────────────────────────────────────────────────────
const T = {
  bg:         'var(--ui-bg)',
  s1:         'var(--ui-surface-1)',
  s2:         'var(--ui-surface-2)',
  s3:         'var(--ui-surface-3)',
  border:     'var(--ui-border-soft)',
  accent:     'var(--ui-accent)',
  accentSoft: 'var(--ui-accent-soft)',
  text:       'var(--ui-text)',
  dim:        'var(--ui-text-dim)',
  meta:       'var(--ui-text-meta)',
  mono:       "'IBM Plex Mono', monospace",
  sans:       "'Manrope', 'Segoe UI', system-ui, sans-serif",
}

const WEEKDAY_SHORT = ['Seg','Ter','Qua','Qui','Sex','Sáb','Dom']
const MONTH_NAMES = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']
type Tab = 'agenda' | 'tarefas' | 'metas'

// ── Date helpers ──────────────────────────────────────────────────────────────
function toDateKey(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
}
function startOfWeek(d: Date): Date {
  const day = d.getDay()
  const r = new Date(d)
  r.setDate(d.getDate() + (day === 0 ? -6 : 1 - day))
  r.setHours(0,0,0,0)
  return r
}
function isToday(d: Date) {
  const n = new Date()
  return d.getDate() === n.getDate() && d.getMonth() === n.getMonth() && d.getFullYear() === n.getFullYear()
}
function buildMonthGrid(cursor: Date): Date[] {
  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1)
  const startOffset = (first.getDay() + 6) % 7
  const gridStart = new Date(first)
  gridStart.setDate(first.getDate() - startOffset)
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(gridStart)
    d.setDate(gridStart.getDate() + i)
    return d
  })
}

// ── Primitives ─────────────────────────────────────────────────────────────────
function SLabel({ children }: { children: string }) {
  return <div style={{ fontSize: 10, fontFamily: T.mono, letterSpacing: '0.16em', textTransform: 'uppercase', color: T.meta, marginBottom: 8 }}>{children}</div>
}
function Card({ children, style }: { children: React.ReactNode; style?: CSSProperties }) {
  return <div style={{ background: T.s1, border: `1px solid ${T.border}`, borderRadius: 14, overflow: 'hidden', ...style }}>{children}</div>
}
function Skel({ h = 56, mb = 8 }: { h?: number; mb?: number }) {
  return <div style={{ height: h, borderRadius: 10, background: T.s2, marginBottom: mb }} />
}

// ── Month picker overlay ───────────────────────────────────────────────────────
function MonthPicker({ initial, onSelect, onClose }: { initial: Date; onSelect: (key: string) => void; onClose: () => void }) {
  const [cursor, setCursor] = useState(() => new Date(initial.getFullYear(), initial.getMonth(), 1))
  const grid = useMemo(() => buildMonthGrid(cursor), [cursor])
  const todayKey = toDateKey(new Date())

  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 50 }} />
      <div style={{
        position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 51,
        background: T.s1, borderRadius: '20px 20px 0 0',
        padding: '16px 16px calc(24px + env(safe-area-inset-bottom,0px))',
        maxHeight: '80vh', overflow: 'hidden',
        animation: 'slideUp .22s ease-out',
      }}>
        <div style={{ width: 36, height: 4, borderRadius: 2, background: T.border, margin: '0 auto 16px' }} />

        {/* Month nav */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <button onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth()-1, 1))} style={navBtn}>
            <ChevronLeft size={16} />
          </button>
          <span style={{ fontSize: 15, fontWeight: 700, color: T.text }}>
            {MONTH_NAMES[cursor.getMonth()]} {cursor.getFullYear()}
          </span>
          <button onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth()+1, 1))} style={navBtn}>
            <ChevronRight size={16} />
          </button>
        </div>

        {/* Day headers */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', marginBottom: 6 }}>
          {WEEKDAY_SHORT.map(d => (
            <div key={d} style={{ textAlign: 'center', fontSize: 10, fontFamily: T.mono, letterSpacing: '0.1em', textTransform: 'uppercase', color: T.meta, paddingBottom: 6 }}>
              {d.slice(0,1)}
            </div>
          ))}
        </div>

        {/* Day cells */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2 }}>
          {grid.map((day, i) => {
            const key = toDateKey(day)
            const inMonth = day.getMonth() === cursor.getMonth()
            const today = key === todayKey
            return (
              <button
                key={i}
                onClick={() => { onSelect(key); onClose() }}
                style={{
                  height: 38, borderRadius: 8, border: 'none', cursor: 'pointer',
                  background: today ? T.accent : 'transparent',
                  color: today ? T.bg : inMonth ? T.text : T.meta,
                  fontSize: 13, fontWeight: today ? 800 : inMonth ? 500 : 400,
                  opacity: inMonth ? 1 : 0.35,
                }}
              >
                {day.getDate()}
              </button>
            )
          })}
        </div>
      </div>
      <style>{`@keyframes slideUp { from { transform: translateY(100%) } to { transform: translateY(0) } }`}</style>
    </>
  )
}

const navBtn: CSSProperties = {
  width: 34, height: 34, borderRadius: 999, background: T.s2,
  border: `1px solid ${T.border}`, color: T.dim, display: 'flex',
  alignItems: 'center', justifyContent: 'center', cursor: 'pointer',
}

// ── Week strip ─────────────────────────────────────────────────────────────────
function WeekStrip({ weekStart, selectedKey, onSelect, onPrev, onNext }: {
  weekStart: Date; selectedKey: string
  onSelect: (key: string) => void
  onPrev: () => void; onNext: () => void
}) {
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(weekStart)
    d.setDate(weekStart.getDate() + i)
    return d
  })
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
      <button onClick={onPrev} style={{ ...navBtn, flexShrink: 0, width: 28, height: 28 }}>
        <ChevronLeft size={13} />
      </button>
      <div style={{ flex: 1, display: 'flex', justifyContent: 'space-around' }}>
        {days.map((day, i) => {
          const key = toDateKey(day)
          const sel = key === selectedKey
          const tod = isToday(day)
          return (
            <button key={key} onClick={() => onSelect(key)} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, background: 'transparent', border: 'none', cursor: 'pointer', padding: '2px 0' }}>
              <span style={{ fontSize: 9, fontFamily: T.mono, textTransform: 'uppercase', color: tod ? T.accent : i >= 5 ? T.meta : T.dim, fontWeight: tod ? 700 : 500 }}>
                {WEEKDAY_SHORT[i].slice(0,1)}
              </span>
              <span style={{
                width: 32, height: 32, borderRadius: '50%',
                background: sel ? T.accent : tod ? T.accentSoft : 'transparent',
                color: sel ? T.bg : tod ? T.accent : i >= 5 ? T.meta : T.text,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 13, fontWeight: sel || tod ? 800 : 500,
                border: tod && !sel ? `1.5px solid ${T.accent}` : 'none',
                transition: 'background .15s',
              }}>
                {day.getDate()}
              </span>
            </button>
          )
        })}
      </div>
      <button onClick={onNext} style={{ ...navBtn, flexShrink: 0, width: 28, height: 28 }}>
        <ChevronRight size={13} />
      </button>
    </div>
  )
}

// ── New task sheet ─────────────────────────────────────────────────────────────
function NewTaskSheet({ onClose, onCreate }: { onClose: () => void; onCreate: (title: string, priority: string) => void }) {
  const [title, setTitle] = useState('')
  const [priority, setPriority] = useState('normal')
  const inputStyle: CSSProperties = { width: '100%', boxSizing: 'border-box', background: T.s2, border: `1px solid ${T.border}`, borderRadius: 10, padding: '10px 12px', fontSize: 14, color: T.text, fontFamily: T.sans, outline: 'none' }
  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 40 }} />
      <div style={{ position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 41, background: T.s1, borderRadius: '20px 20px 0 0', padding: '20px 20px calc(20px + env(safe-area-inset-bottom,0px))', animation: 'slideUp .22s ease-out' }}>
        <div style={{ width: 36, height: 4, borderRadius: 2, background: T.border, margin: '0 auto 18px' }} />
        <div style={{ fontSize: 10, fontFamily: T.mono, letterSpacing: '0.16em', textTransform: 'uppercase', color: T.meta, marginBottom: 6 }}>Nova tarefa</div>
        <h3 style={{ fontSize: 18, fontWeight: 800, color: T.text, margin: '0 0 16px', letterSpacing: '-0.02em' }}>O que precisa ser feito?</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <input autoFocus value={title} onChange={e => setTitle(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && title.trim()) { onCreate(title.trim(), priority); onClose() } }} placeholder="Título da tarefa" style={inputStyle} />
          <div style={{ display: 'flex', gap: 6 }}>
            {(['high','normal','low'] as const).map(p => (
              <button key={p} onClick={() => setPriority(p)} style={{ flex: 1, height: 36, borderRadius: 8, border: `1px solid ${priority === p ? T.accent : T.border}`, background: priority === p ? T.accentSoft : T.s2, color: priority === p ? T.accent : T.dim, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                {p === 'high' ? 'Alta' : p === 'normal' ? 'Normal' : 'Baixa'}
              </button>
            ))}
          </div>
          <button onClick={() => { if (!title.trim()) return; onCreate(title.trim(), priority); onClose() }} disabled={!title.trim()} style={{ width: '100%', height: 46, borderRadius: 12, background: title.trim() ? T.accent : T.s3, color: title.trim() ? T.bg : T.dim, border: 'none', fontSize: 14, fontWeight: 700, cursor: title.trim() ? 'pointer' : 'not-allowed', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
            <Plus size={16} /> Criar tarefa
          </button>
        </div>
      </div>
    </>
  )
}

// ── New reminder sheet ─────────────────────────────────────────────────────────
function NewReminderSheet({ defaultDate, onClose, onCreate }: { defaultDate: string; onClose: () => void; onCreate: (title: string, date: string, time: string) => void }) {
  const [title, setTitle] = useState('')
  const [time, setTime] = useState('09:00')
  const inputStyle: CSSProperties = { width: '100%', boxSizing: 'border-box', background: T.s2, border: `1px solid ${T.border}`, borderRadius: 10, padding: '10px 12px', fontSize: 14, color: T.text, fontFamily: T.sans, outline: 'none' }
  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 40 }} />
      <div style={{ position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 41, background: T.s1, borderRadius: '20px 20px 0 0', padding: '20px 20px calc(20px + env(safe-area-inset-bottom,0px))', animation: 'slideUp .22s ease-out' }}>
        <div style={{ width: 36, height: 4, borderRadius: 2, background: T.border, margin: '0 auto 18px' }} />
        <div style={{ fontSize: 10, fontFamily: T.mono, letterSpacing: '0.16em', textTransform: 'uppercase', color: T.meta, marginBottom: 14 }}>Novo lembrete</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <input autoFocus value={title} onChange={e => setTitle(e.target.value)} placeholder="Título do lembrete" style={inputStyle} />
          <input type="time" value={time} onChange={e => setTime(e.target.value)} style={{ ...inputStyle, colorScheme: 'dark' }} />
          <button onClick={() => { if (!title.trim()) return; onCreate(title.trim(), defaultDate, time); onClose() }} disabled={!title.trim()} style={{ width: '100%', height: 46, borderRadius: 12, background: title.trim() ? T.accent : T.s3, color: title.trim() ? T.bg : T.dim, border: 'none', fontSize: 14, fontWeight: 700, cursor: title.trim() ? 'pointer' : 'not-allowed' }}>
            Salvar lembrete
          </button>
        </div>
      </div>
    </>
  )
}

// ── Agenda tab ─────────────────────────────────────────────────────────────────
function AgendaTab({ selectedKey, selectedWeekday }: { selectedKey: string; selectedWeekday: number }) {
  const qc = useQueryClient()
  const [showReminder, setShowReminder] = useState(false)

  const { data: schedules } = useQuery<ScheduleItem[]>({ queryKey: ['calendar-schedules'], queryFn: () => apiClient.listSchedules(false), retry: 1 })
  const { data: dayReminders, isLoading: remLoad } = useQuery<ReminderItem[]>({
    queryKey: ['calendar-reminders', selectedKey],
    queryFn: () => apiClient.listReminders(`${selectedKey}T00:00:00`, `${selectedKey}T23:59:59`),
    retry: 1,
  })
  const { data: overview } = useQuery({
    queryKey: ['calendar-overview', selectedKey],
    queryFn: () => apiClient.getCalendarOverview(selectedKey),
    retry: 1,
  })

  const daySchedule = useMemo(
    () => (schedules ?? []).filter(s => s.day_of_week === selectedWeekday && s.active).sort((a, b) => a.start_time.localeCompare(b.start_time)),
    [schedules, selectedWeekday],
  )

  const deleteReminder = useMutation({
    mutationFn: (id: number) => apiClient.deleteReminder(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['calendar-reminders'] }); toast.success('Lembrete removido') },
    onError: () => toast.error('Erro ao remover lembrete'),
  })

  const createReminder = useMutation({
    mutationFn: ({ title, date, time }: { title: string; date: string; time: string }) =>
      apiClient.createReminder({ title, starts_at: new Date(`${date}T${time}:00`).toISOString(), ends_at: null, note: null, all_day: false }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['calendar-reminders'] }); toast.success('Lembrete salvo') },
    onError: () => toast.error('Erro ao salvar lembrete'),
  })

  const liveNow = overview?.current_schedule_item
  const nextItem = overview?.next_schedule_item

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Live now */}
      {(liveNow || nextItem) && (
        <div style={{ background: T.accentSoft, border: `1px solid color-mix(in srgb, ${T.accent} 30%, transparent)`, borderRadius: 12, padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: T.accent, flexShrink: 0, boxShadow: `0 0 8px ${T.accent}` }} />
          <div>
            <div style={{ fontSize: 9, fontFamily: T.mono, letterSpacing: '0.12em', textTransform: 'uppercase', color: T.accent }}>{liveNow ? 'Agora' : 'Próxima'}</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{liveNow ? `${liveNow.title} até ${liveNow.end_time}` : `${nextItem!.title} às ${nextItem!.start_time}`}</div>
          </div>
        </div>
      )}

      {/* Schedule */}
      <div>
        <SLabel>Agenda do dia</SLabel>
        {daySchedule.length === 0 ? (
          <div style={{ background: T.s1, border: `1px solid ${T.border}`, borderRadius: 12, padding: 14, color: T.meta, fontSize: 12, textAlign: 'center' }}>
            Nenhum bloco para {WEEKDAY_SHORT[selectedWeekday]}
          </div>
        ) : (
          <Card>
            {daySchedule.map((item, i) => (
              <div key={item.id} style={{ display: 'flex', gap: 10, padding: '11px 14px', borderBottom: i < daySchedule.length - 1 ? `1px solid ${T.border}` : 'none', alignItems: 'flex-start' }}>
                <div style={{ flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1, paddingTop: 2, minWidth: 36 }}>
                  <span style={{ fontSize: 11, fontFamily: T.mono, color: T.meta }}>{item.start_time}</span>
                  <div style={{ width: 1, height: 8, background: T.border }} />
                  <span style={{ fontSize: 10, fontFamily: T.mono, color: T.meta }}>{item.end_time}</span>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{item.title}</div>
                  {item.note && <div style={{ fontSize: 11, color: T.dim, marginTop: 2 }}>{item.note}</div>}
                </div>
              </div>
            ))}
          </Card>
        )}
      </div>

      {/* Reminders */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <SLabel>Lembretes</SLabel>
          <button onClick={() => setShowReminder(true)} style={{ background: 'none', border: 'none', fontSize: 11, color: T.accent, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 3 }}>
            <Plus size={11} /> Novo
          </button>
        </div>
        {remLoad ? <Skel /> : !dayReminders || dayReminders.length === 0 ? (
          <div style={{ background: T.s1, border: `1px dashed ${T.border}`, borderRadius: 12, padding: 14, color: T.meta, fontSize: 12, textAlign: 'center' }}>
            Sem lembretes para este dia
          </div>
        ) : (
          <Card>
            {dayReminders.map((r, i) => (
              <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '11px 14px', borderBottom: i < dayReminders.length - 1 ? `1px solid ${T.border}` : 'none' }}>
                <Bell size={13} color={T.accent} style={{ flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{r.title}</div>
                  <div style={{ fontSize: 10, color: T.meta, fontFamily: T.mono }}>{r.all_day ? 'Dia inteiro' : new Date(r.starts_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</div>
                </div>
                <button onClick={() => deleteReminder.mutate(r.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.meta, padding: 4, display: 'flex' }}>
                  ×
                </button>
              </div>
            ))}
          </Card>
        )}
      </div>

      {showReminder && (
        <NewReminderSheet
          defaultDate={selectedKey}
          onClose={() => setShowReminder(false)}
          onCreate={(title, date, time) => createReminder.mutate({ title, date, time })}
        />
      )}
    </div>
  )
}

// ── Tarefas tab ────────────────────────────────────────────────────────────────
type TaskFilter = 'all' | 'doing' | 'pending' | 'done'
const FILTER_LABELS: Record<TaskFilter, string> = { all: 'Todas', doing: 'Ativas', pending: 'Pendentes', done: 'Concluídas' }

function TarefasTab({ onOpenNew }: { onOpenNew: () => void }) {
  const qc = useQueryClient()
  const [filter, setFilter] = useState<TaskFilter>('all')

  const { data: tasks = [], isLoading } = useQuery<TaskItem[]>({ queryKey: ['tasks'], queryFn: () => apiClient.listTasks(), retry: 1 })

  const toggleTask = useMutation({
    mutationFn: ({ task, status }: { task: TaskItem; status: string }) =>
      apiClient.updateTask(task.id, task.title, task.note ?? undefined, status, task.priority, task.due_date ?? undefined),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }),
    onError: () => toast.error('Erro ao atualizar tarefa'),
  })

  const deleteTask = useMutation({
    mutationFn: (id: number) => apiClient.deleteTask(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tasks'] }); toast.success('Tarefa removida') },
    onError: () => toast.error('Erro ao remover tarefa'),
  })

  const filtered = useMemo(() => {
    const base = filter === 'all' ? tasks : tasks.filter(t => t.status === filter)
    return [...base].sort((a, b) => {
      const so: Record<string, number> = { doing: 0, pending: 1, done: 2 }
      const sd = (so[a.status] ?? 99) - (so[b.status] ?? 99)
      if (sd !== 0) return sd
      const po = (p: string) => p === 'high' ? 0 : p === 'normal' ? 1 : 2
      return po(a.priority) - po(b.priority)
    })
  }, [tasks, filter])

  const counts = useMemo(() => ({
    all: tasks.length, doing: tasks.filter(t => t.status === 'doing').length,
    pending: tasks.filter(t => t.status === 'pending').length, done: tasks.filter(t => t.status === 'done').length,
  }), [tasks])

  function nextStatus(s: string) {
    return s === 'pending' ? 'doing' : s === 'doing' ? 'done' : 'pending'
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Filter pills */}
      <div style={{ display: 'flex', gap: 6, overflowX: 'auto', scrollbarWidth: 'none', paddingBottom: 2 }}>
        {(['all','doing','pending','done'] as TaskFilter[]).map(f => (
          <button key={f} onClick={() => setFilter(f)} style={{ flexShrink: 0, padding: '6px 12px', borderRadius: 999, border: 'none', background: filter === f ? T.accent : T.s2, color: filter === f ? T.bg : T.dim, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
            {FILTER_LABELS[f]} {counts[f] > 0 ? `(${counts[f]})` : ''}
          </button>
        ))}
      </div>

      {/* Quick add */}
      <button onClick={onOpenNew} style={{ display: 'flex', alignItems: 'center', gap: 10, background: T.s1, border: `1px dashed ${T.border}`, borderRadius: 12, padding: '12px 14px', cursor: 'pointer', color: T.meta, fontSize: 13 }}>
        <Plus size={14} color={T.accent} />
        Nova tarefa...
      </button>

      {/* List */}
      {isLoading ? (
        <><Skel /><Skel /><Skel /></>
      ) : filtered.length === 0 ? (
        <div style={{ background: T.s1, border: `1px solid ${T.border}`, borderRadius: 12, padding: '24px 14px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
          <Check size={22} color='#34d399' />
          <span style={{ fontSize: 13, color: T.dim }}>Nenhuma tarefa para exibir.</span>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {filtered.map(task => {
            const overdue = task.due_date && task.status !== 'done' && new Date(task.due_date).getTime() < Date.now()
            const done = task.status === 'done'
            return (
              <div key={task.id} style={{ background: T.s1, border: `1px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
                <button onClick={() => toggleTask.mutate({ task, status: nextStatus(task.status) })} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, flexShrink: 0, display: 'flex' }}>
                  {done ? <CheckCircle2 size={18} color='#34d399' /> : task.status === 'doing' ? <CheckCircle2 size={18} color={T.accent} /> : <Circle size={18} color={T.meta} />}
                </button>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: done ? T.meta : T.text, textDecoration: done ? 'line-through' : 'none', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {task.title}
                  </div>
                  {task.due_date && (
                    <div style={{ fontSize: 10, fontFamily: T.mono, color: overdue ? '#f87171' : T.meta, marginTop: 2, display: 'flex', alignItems: 'center', gap: 3 }}>
                      {overdue && <AlertTriangle size={9} />}
                      {new Date(task.due_date).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })}
                    </div>
                  )}
                </div>
                {task.status === 'doing' && (
                  <span style={{ fontSize: 9, fontFamily: T.mono, letterSpacing: '0.1em', textTransform: 'uppercase', color: T.accent, background: T.accentSoft, borderRadius: 4, padding: '2px 6px', flexShrink: 0 }}>ativo</span>
                )}
                <button onClick={() => deleteTask.mutate(task.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.meta, padding: 4, display: 'flex', flexShrink: 0 }}>
                  <Trash2 size={13} />
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Metas tab ──────────────────────────────────────────────────────────────────
function MetasTab() {
  const { data: plans = [], isLoading } = useQuery<StudyPlanItem[]>({
    queryKey: ['study-plans'],
    queryFn: apiClient.listStudyPlans,
    retry: 1,
  })
  const qc = useQueryClient()

  const deleteplan = useMutation({
    mutationFn: (id: number) => apiClient.deleteStudyPlan(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['study-plans'] }); toast.success('Plano removido') },
  })

  function daysLeft(deadline: string) {
    const diff = Math.ceil((new Date(`${deadline}T00:00:00`).getTime() - Date.now()) / 86400000)
    return diff
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontSize: 12, color: T.dim, lineHeight: 1.5 }}>
        Planos de estudo gerados a partir dos seus documentos. Para criar um novo, acesse a versão desktop.
      </div>
      {isLoading ? (
        <><Skel /><Skel /></>
      ) : plans.length === 0 ? (
        <div style={{ background: T.s1, border: `1px solid ${T.border}`, borderRadius: 12, padding: '20px 14px', textAlign: 'center' }}>
          <BookOpen size={24} color={T.meta} style={{ margin: '0 auto 8px' }} />
          <div style={{ fontSize: 13, color: T.dim }}>Nenhum plano criado ainda.</div>
        </div>
      ) : (
        plans.map(plan => {
          const left = daysLeft(plan.deadline_date)
          const expired = left < 0
          return (
            <div key={plan.id} style={{ background: T.s1, border: `1px solid ${T.border}`, borderRadius: 12, padding: '14px 14px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{plan.titulo}</div>
                  <div style={{ fontSize: 11, color: T.meta, marginTop: 2 }}>{plan.doc_name}</div>
                </div>
                <button onClick={() => deleteplan.mutate(plan.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.meta, padding: 4, display: 'flex' }}>
                  <Trash2 size={13} />
                </button>
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 11, background: T.s2, borderRadius: 6, padding: '3px 8px', color: expired ? '#f87171' : left <= 7 ? '#fbbf24' : '#34d399' }}>
                  {expired ? 'Prazo expirado' : `${left} dias restantes`}
                </span>
                <span style={{ fontSize: 11, background: T.s2, borderRadius: 6, padding: '3px 8px', color: T.dim }}>
                  {plan.hours_per_day}h/dia · {plan.tasks_created} tarefas
                </span>
              </div>
            </div>
          )
        })
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export function MobileCalendario() {
  const qc = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [tab, setTab] = useState<Tab>('agenda')
  const [selectedKey, setSelectedKey] = useState(() => toDateKey(new Date()))
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()))
  const [showMonthPicker, setShowMonthPicker] = useState(false)
  const [showNewTask, setShowNewTask] = useState(() => searchParams.get('new') === '1')

  // Sync FAB ?new=1 param with sheet
  if (searchParams.get('new') === '1' && !showNewTask) {
    setShowNewTask(true)
    setSearchParams({}, { replace: true })
  }

  function handleSelectDay(key: string) {
    setSelectedKey(key)
    const d = new Date(`${key}T00:00:00`)
    setWeekStart(startOfWeek(d))
  }

  function prevWeek() {
    const ws = new Date(weekStart)
    ws.setDate(ws.getDate() - 7)
    setWeekStart(ws)
  }

  function nextWeek() {
    const ws = new Date(weekStart)
    ws.setDate(ws.getDate() + 7)
    setWeekStart(ws)
  }

  const selectedDateObj = new Date(`${selectedKey}T00:00:00`)
  const monthLabel = `${MONTH_NAMES[weekStart.getMonth()]} ${weekStart.getFullYear()}`

  const selectedWeekday = useMemo(() => {
    const js = selectedDateObj.getDay()
    return js === 0 ? 6 : js - 1
  }, [selectedKey])

  const createTask = useMutation({
    mutationFn: ({ title, priority }: { title: string; priority: string }) => apiClient.createTask(title, undefined, priority, undefined),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tasks'] }); toast.success('Tarefa criada') },
    onError: () => toast.error('Erro ao criar tarefa'),
  })

  const TABS: { key: Tab; label: string }[] = [
    { key: 'agenda', label: 'Agenda' },
    { key: 'tarefas', label: 'Tarefas' },
    { key: 'metas', label: 'Metas' },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', fontFamily: T.sans, height: '100%' }}>

      {/* ── Calendar header (sticky) ─────────────────────────────────────── */}
      <div style={{ padding: '12px 16px 0', background: T.bg, flexShrink: 0 }}>
        {/* Month nav */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <button onClick={prevWeek} style={navBtn}><ChevronLeft size={15} /></button>
          <button
            onClick={() => setShowMonthPicker(true)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, color: T.text, fontSize: 15, fontWeight: 700 }}
          >
            <Clock size={14} color={T.accent} />
            {monthLabel}
          </button>
          <button onClick={nextWeek} style={navBtn}><ChevronRight size={15} /></button>
        </div>

        {/* Week strip */}
        <WeekStrip weekStart={weekStart} selectedKey={selectedKey} onSelect={handleSelectDay} onPrev={prevWeek} onNext={nextWeek} />

        {/* Selected day label */}
        <div style={{ fontSize: 12, color: T.dim, marginTop: 6, marginBottom: 10, textTransform: 'capitalize' }}>
          {selectedDateObj.toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' })}
        </div>

        {/* Tab bar */}
        <div style={{ display: 'flex', borderBottom: `1px solid ${T.border}` }}>
          {TABS.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)} style={{
              flex: 1, padding: '8px 0', background: 'none', border: 'none', cursor: 'pointer',
              fontSize: 13, fontWeight: tab === t.key ? 700 : 500,
              color: tab === t.key ? T.accent : T.dim,
              borderBottom: tab === t.key ? `2px solid ${T.accent}` : '2px solid transparent',
              transition: 'color .15s',
            }}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Scrollable content ───────────────────────────────────────────── */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 16px 100px' }}>
        {tab === 'agenda' && <AgendaTab selectedKey={selectedKey} selectedWeekday={selectedWeekday} />}
        {tab === 'tarefas' && <TarefasTab onOpenNew={() => setShowNewTask(true)} />}
        {tab === 'metas' && <MetasTab />}
      </div>

      {/* ── Month picker ─────────────────────────────────────────────────── */}
      {showMonthPicker && (
        <MonthPicker
          initial={selectedDateObj}
          onSelect={handleSelectDay}
          onClose={() => setShowMonthPicker(false)}
        />
      )}

      {/* ── New task sheet ───────────────────────────────────────────────── */}
      {showNewTask && (
        <NewTaskSheet
          onClose={() => setShowNewTask(false)}
          onCreate={(title, priority) => createTask.mutate({ title, priority })}
        />
      )}

      <style>{`@keyframes slideUp { from { transform: translateY(100%) } to { transform: translateY(0) } }`}</style>
    </div>
  )
}
