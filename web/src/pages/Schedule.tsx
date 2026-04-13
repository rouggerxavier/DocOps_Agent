import { useMemo, useState, useRef, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Clock, Plus, Sparkles, ChevronLeft, ChevronRight,
  Bell, AlignJustify, Calendar, Check, X, Pencil, Trash2,
} from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  apiClient,
  type CalendarOverview,
  type ReminderItem,
  type ScheduleItem,
} from '@/api/client'
import { cn } from '@/lib/utils'

const WEEKDAY_LABELS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
const WEEKDAY_FULL = [
  'Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira',
  'Sexta-feira', 'Sábado', 'Domingo',
]
const MONTH_NAMES = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
]

const EVENT_COLORS = [
  'border-l-[color:var(--ui-accent)] bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent)]',
  'border-l-emerald-400 bg-emerald-500/12 text-emerald-300',
  'border-l-violet-400 bg-violet-500/12 text-violet-300',
  'border-l-amber-400 bg-amber-500/12 text-amber-300',
  'border-l-cyan-400 bg-cyan-500/12 text-cyan-300',
  'border-l-rose-400 bg-rose-500/12 text-rose-300',
]

const EVENT_BG_COLORS = [
  'bg-[color:var(--ui-accent-soft)] border-l-[color:var(--ui-accent)] text-[color:var(--ui-text)]',
  'bg-emerald-500/14 border-l-emerald-400 text-emerald-100',
  'bg-violet-500/14 border-l-violet-400 text-violet-100',
  'bg-amber-500/14 border-l-amber-400 text-amber-100',
  'bg-rose-500/14 border-l-rose-400 text-rose-100',
  'bg-cyan-500/14 border-l-cyan-400 text-cyan-100',
]

// Hora de início do grid semanal (6h da manhã)
const WEEK_START_HOUR = 6
// Hora de fim do grid semanal (23h)
const WEEK_END_HOUR = 23
// Altura em pixels por hora
const HOUR_HEIGHT = 56

function toDateKey(d: Date) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function startOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}

function endOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0)
}

/** Retorna a segunda-feira da semana que contém `d` */
function startOfWeek(d: Date): Date {
  const day = d.getDay() // 0=dom
  const diff = day === 0 ? -6 : 1 - day
  const result = new Date(d)
  result.setDate(d.getDate() + diff)
  result.setHours(0, 0, 0, 0)
  return result
}

function buildMonthGrid(monthDate: Date): Date[] {
  const first = startOfMonth(monthDate)
  const last = endOfMonth(monthDate)
  const startOffset = (first.getDay() + 6) % 7
  const gridStart = new Date(first)
  gridStart.setDate(first.getDate() - startOffset)

  const days: Date[] = []
  for (let i = 0; i < 42; i++) {
    const cell = new Date(gridStart)
    cell.setDate(gridStart.getDate() + i)
    days.push(cell)
  }
  if (days[41] < last) {
    for (let i = 42; i < 49; i++) {
      const cell = new Date(gridStart)
      cell.setDate(gridStart.getDate() + i)
      days.push(cell)
    }
  }
  return days
}

function isoFromDateAndTime(dateStr: string, timeStr: string) {
  return new Date(`${dateStr}T${timeStr}:00`).toISOString()
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

function isToday(d: Date) {
  const now = new Date()
  return d.getDate() === now.getDate() && d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear()
}

/** Converte "HH:MM" para minutos desde meia-noite */
function timeToMinutes(t: string): number {
  const [h, m] = t.split(':').map(Number)
  return h * 60 + (m || 0)
}

/** Posição top em px dentro do grid de horas */
function minutesToTop(minutes: number): number {
  const startMinutes = WEEK_START_HOUR * 60
  return ((minutes - startMinutes) / 60) * HOUR_HEIGHT
}

/** Altura em px para uma duração em minutos */
function durationToHeight(startMinutes: number, endMinutes: number): number {
  const dur = Math.max(endMinutes - startMinutes, 30)
  return (dur / 60) * HOUR_HEIGHT
}

// ── Mini pill para evento dentro da célula mensal ─────────────────────────
function EventPill({ title, colorIdx }: { title: string; colorIdx: number }) {
  const cls = EVENT_COLORS[colorIdx % EVENT_COLORS.length]
  return (
    <div className={cn('truncate rounded-r-sm border-l-2 px-1.5 py-0.5 text-[10px] font-medium leading-none', cls)}>
      {title}
    </div>
  )
}

// ── Card de lembrete na lista lateral ──────────────────────────────────────
function ReminderCard({ reminder, onDelete }: { reminder: ReminderItem; onDelete: () => void }) {
  return (
    <div className="group flex items-start gap-3 rounded-xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)]/45 p-3 transition-all hover:border-[color:var(--ui-border-strong)] hover:bg-[color:var(--ui-surface-2)]">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[color:var(--ui-accent-soft)]">
        <Bell className="h-3.5 w-3.5 text-[color:var(--ui-accent)]" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="truncate text-sm font-semibold text-[color:var(--ui-text)]">{reminder.title}</p>
        <p className="text-xs text-[color:var(--ui-text-meta)]">
          {reminder.all_day ? 'Dia inteiro' : formatTime(reminder.starts_at)}
          {reminder.note ? ` · ${reminder.note}` : ''}
        </p>
      </div>
      <button
        onClick={onDelete}
        className="shrink-0 text-[color:var(--ui-text-meta)] transition-opacity hover:text-rose-400 sm:opacity-0 sm:group-hover:opacity-100"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}

// ── Card de bloco fixo na lista lateral ────────────────────────────────────
function ScheduleCard({ item, onDelete, colorIdx }: { item: ScheduleItem; onDelete: () => void; colorIdx: number }) {
  const cls = EVENT_COLORS[colorIdx % EVENT_COLORS.length]
  return (
    <div className="group flex items-start gap-3 rounded-xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)]/45 p-3 transition-all hover:border-[color:var(--ui-border-strong)] hover:bg-[color:var(--ui-surface-2)]">
      <div className={cn('mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border', cls)}>
        <Clock className="h-3.5 w-3.5" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="truncate text-sm font-semibold text-[color:var(--ui-text)]">{item.title}</p>
        <p className="text-xs text-[color:var(--ui-text-meta)]">
          {item.start_time} – {item.end_time}
          {item.note ? ` · ${item.note}` : ''}
        </p>
      </div>
      <button
        onClick={onDelete}
        className="shrink-0 text-[color:var(--ui-text-meta)] transition-opacity hover:text-rose-400 sm:opacity-0 sm:group-hover:opacity-100"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}

// ── Formulário expansível ──────────────────────────────────────────────────
function CollapsibleForm({
  title, icon, color, children, defaultOpen = false
}: {
  title: string
  icon: React.ReactNode
  color: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="overflow-hidden rounded-2xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-1)]">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-[color:var(--ui-surface-2)]"
      >
        <div className={cn('flex h-7 w-7 shrink-0 items-center justify-center rounded-full', color)}>
          {icon}
        </div>
        <span className="flex-1 text-sm font-semibold text-[color:var(--ui-text)]">{title}</span>
        <Plus className={cn('h-4 w-4 text-[color:var(--ui-text-meta)] transition-transform', open && 'rotate-45')} />
      </button>
      {open && (
        <div className="space-y-3 border-t border-[color:var(--ui-border-soft)] px-4 pb-4 pt-3">
          {children}
        </div>
      )}
    </div>
  )
}

// ── Tipo de item selecionado no grid ──────────────────────────────────────
type SelectedBlock =
  | { kind: 'schedule'; item: ScheduleItem; colorIdx: number; x: number; y: number }
  | { kind: 'reminder'; item: ReminderItem; x: number; y: number }

// ── Popover de edição de bloco ────────────────────────────────────────────
function BlockPopover({
  block,
  onClose,
  onDeleteSchedule,
  onDeleteReminder,
  onUpdateSchedule,
  onUpdateReminder,
}: {
  block: SelectedBlock
  onClose: () => void
  onDeleteSchedule: (id: number) => void
  onDeleteReminder: (id: number) => void
  onUpdateSchedule: (id: number, payload: { title: string; day_of_week: number; start_time: string; end_time: string; note?: string | null }) => void
  onUpdateReminder: (id: number, payload: { title: string; starts_at: string; ends_at?: string | null; note?: string | null }) => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [editing, setEditing] = useState(false)
  const [confirming, setConfirming] = useState(false)

  // Campos editáveis
  const [title, setTitle] = useState(block.kind === 'schedule' ? block.item.title : block.item.title)
  const [startTime, setStartTime] = useState(
    block.kind === 'schedule'
      ? block.item.start_time
      : new Date(block.item.starts_at).toTimeString().slice(0, 5)
  )
  const [endTime, setEndTime] = useState(
    block.kind === 'schedule'
      ? block.item.end_time
      : block.item.ends_at
        ? new Date(block.item.ends_at).toTimeString().slice(0, 5)
        : new Date(new Date(block.item.starts_at).getTime() + 3600000).toTimeString().slice(0, 5)
  )
  const [note, setNote] = useState(
    block.kind === 'schedule' ? (block.item.note ?? '') : (block.item.note ?? '')
  )

  // Fecha ao clicar fora
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onClose])

  // Posição: garante que não saia da tela
  const style: React.CSSProperties = {
    position: 'fixed',
    zIndex: 50,
    top: Math.min(block.y, window.innerHeight - 320),
    left: Math.min(block.x, window.innerWidth - 260),
  }

  const colorCls = block.kind === 'schedule'
    ? EVENT_BG_COLORS[block.colorIdx % EVENT_BG_COLORS.length]
    : 'bg-blue-500/15 border-blue-500/40 text-blue-200'

  function handleSave() {
    if (block.kind === 'schedule') {
      onUpdateSchedule(block.item.id, { title, day_of_week: block.item.day_of_week, start_time: startTime, end_time: endTime, note: note || null })
    } else {
      const dateStr = toDateKey(new Date(block.item.starts_at))
      onUpdateReminder(block.item.id, {
        title,
        starts_at: new Date(`${dateStr}T${startTime}:00`).toISOString(),
        ends_at: new Date(`${dateStr}T${endTime}:00`).toISOString(),
        note: note || null,
      })
    }
    setEditing(false)
  }

  return (
    <div ref={ref} style={style} className="w-60 overflow-hidden rounded-xl border border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-2)] shadow-2xl shadow-black/60">
      {/* Cabeçalho colorido */}
      <div className={cn('flex items-center justify-between border-b border-[color:var(--ui-border-soft)] px-3 py-2', colorCls.split(' ').slice(0, 1).join(' '), 'bg-opacity-30')}>
        <span className="text-xs font-semibold truncate max-w-[160px]">
          {block.kind === 'schedule' ? 'Bloco fixo' : 'Lembrete'}
        </span>
        <button onClick={onClose} className="ml-1 text-[color:var(--ui-text-meta)] hover:text-[color:var(--ui-text)]">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {!editing ? (
        <div className="p-3 space-y-2">
          <p className="text-sm font-semibold leading-tight text-[color:var(--ui-text)]">
            {block.kind === 'schedule' ? block.item.title : block.item.title}
          </p>
          <p className="text-xs text-[color:var(--ui-text-meta)]">
            {block.kind === 'schedule'
              ? `${block.item.start_time} – ${block.item.end_time}`
              : `${startTime} – ${endTime}`}
          </p>
          {(block.kind === 'schedule' ? block.item.note : block.item.note) && (
            <p className="text-xs text-[color:var(--ui-text-dim)]">{block.kind === 'schedule' ? block.item.note : block.item.note}</p>
          )}
          <div className="flex gap-2 pt-1">
            <button
              onClick={() => setEditing(true)}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-3)] py-1.5 text-xs text-[color:var(--ui-text-dim)] transition-colors hover:border-[color:var(--ui-border-strong)] hover:text-[color:var(--ui-text)]"
            >
              <Pencil className="h-3 w-3" /> Editar
            </button>
            {!confirming ? (
              <button
                onClick={() => setConfirming(true)}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-red-800/50 bg-red-950/30 py-1.5 text-xs text-red-400 hover:bg-red-950/60 transition-colors"
              >
                <Trash2 className="h-3 w-3" /> Excluir
              </button>
            ) : (
              <div className="flex flex-1 gap-1">
                <button
                  onClick={() => {
                    if (block.kind === 'schedule') onDeleteSchedule(block.item.id)
                    else onDeleteReminder(block.item.id)
                    onClose()
                  }}
                  className="flex flex-1 items-center justify-center gap-1 rounded-lg border border-red-600 bg-red-600 py-1.5 text-xs font-semibold text-white hover:bg-red-700 transition-colors"
                >
                  <Trash2 className="h-3 w-3" /> Confirmar
                </button>
                <button
                  onClick={() => setConfirming(false)}
                  className="flex items-center justify-center rounded-lg border border-[color:var(--ui-border-strong)] px-2 text-xs text-[color:var(--ui-text-meta)] transition-colors hover:text-[color:var(--ui-text)]"
                >
                  Cancelar
                </button>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="p-3 space-y-2">
          <Input
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="Título"
            className="h-7 border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-3)] text-xs text-[color:var(--ui-text)]"
          />
          <div className="grid grid-cols-2 gap-1.5">
            <Input type="time" value={startTime} onChange={e => setStartTime(e.target.value)} className="h-7 border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-3)] text-xs text-[color:var(--ui-text)]" />
            <Input type="time" value={endTime} onChange={e => setEndTime(e.target.value)} className="h-7 border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-3)] text-xs text-[color:var(--ui-text)]" />
          </div>
          <Input
            value={note}
            onChange={e => setNote(e.target.value)}
            placeholder="Observação (opcional)"
            className="h-7 border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-3)] text-xs text-[color:var(--ui-text)]"
          />
          <div className="flex gap-2">
            <Button size="sm" className="flex-1 h-7 bg-[color:var(--ui-accent)] text-xs text-[color:var(--ui-bg)] hover:bg-[color:var(--ui-accent-strong)]" onClick={handleSave} disabled={!title.trim()}>
              Salvar
            </Button>
            <button
              onClick={() => setEditing(false)}
              className="flex items-center justify-center rounded-lg border border-[color:var(--ui-border-strong)] px-2 text-xs text-[color:var(--ui-text-meta)] hover:text-[color:var(--ui-text)]"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── View Semanal ───────────────────────────────────────────────────────────
function WeekView({
  weekStart,
  reminders,
  schedules,
  selectedDate,
  onSelectDate,
  onBlockClick,
}: {
  weekStart: Date
  reminders: ReminderItem[] | undefined
  schedules: ScheduleItem[] | undefined
  selectedDate: string
  onSelectDate: (key: string) => void
  onBlockClick: (block: SelectedBlock) => void
}) {
  const hours = Array.from({ length: WEEK_END_HOUR - WEEK_START_HOUR + 1 }, (_, i) => WEEK_START_HOUR + i)

  // Os 7 dias da semana (Seg–Dom)
  const weekDays = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(weekStart)
    d.setDate(weekStart.getDate() + i)
    return d
  })

  // Lembretes agrupados por dia
  const remindersByDay = useMemo(() => {
    const map = new Map<string, ReminderItem[]>()
    for (const r of reminders ?? []) {
      const key = toDateKey(new Date(r.starts_at))
      const bucket = map.get(key) ?? []
      bucket.push(r)
      map.set(key, bucket)
    }
    return map
  }, [reminders])

  // Índice de cor por schedule id (estável)
  const scheduleColorMap = useMemo(() => {
    const map = new Map<number, number>()
    let idx = 0
    for (const s of schedules ?? []) {
      map.set(s.id, idx % EVENT_BG_COLORS.length)
      idx++
    }
    return map
  }, [schedules])

  const now = new Date()
  const nowMinutes = now.getHours() * 60 + now.getMinutes()
  const nowTop = minutesToTop(nowMinutes)
  const timeGridStyle: React.CSSProperties = {
    backgroundImage: 'linear-gradient(to bottom, rgba(53, 57, 64, 0.36) 1px, transparent 1px)',
    backgroundSize: `100% ${HOUR_HEIGHT}px`,
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="grid grid-cols-[60px_1fr] border-b border-[color:var(--ui-border-soft)]/70 bg-[color:var(--ui-bg)]">
        <div className="flex h-16 items-center justify-center border-r border-[color:var(--ui-border-soft)]/60 text-[10px] font-semibold tracking-[0.12em] text-[color:var(--ui-text-meta)]">
          GMT-3
        </div>
        <div className="grid grid-cols-7 h-16">
        {weekDays.map((day, i) => {
          const key = toDateKey(day)
          const isSelected = key === selectedDate
          const isTodayDay = isToday(day)
          const isWeekend = i >= 5
          return (
            <button
              key={key}
              onClick={() => onSelectDate(key)}
              className={cn(
                  'relative flex flex-col items-center justify-center border-r border-[color:var(--ui-border-soft)]/40 transition-colors',
                  isSelected
                    ? 'bg-[color:var(--ui-surface-1)]'
                    : isWeekend
                      ? 'bg-[color:var(--ui-bg)]/75 hover:bg-[color:var(--ui-surface-1)]/45'
                      : 'bg-[color:var(--ui-bg)] hover:bg-[color:var(--ui-surface-1)]/35'
              )}
            >
              <span
                className={cn(
                  'text-[10px] font-bold uppercase tracking-[0.14em]',
                  isTodayDay ? 'text-[color:var(--ui-accent)]' : isWeekend ? 'text-[color:var(--ui-text-meta)]/55' : 'text-[color:var(--ui-text-meta)]'
                )}
              >
                {WEEKDAY_LABELS[i]}
              </span>
              <span
                className={cn(
                  'mt-1.5 flex h-8 w-8 items-center justify-center rounded-full text-base font-headline font-bold',
                  isTodayDay
                    ? 'bg-[color:var(--ui-accent)] text-[color:var(--ui-bg)]'
                    : isSelected
                      ? 'bg-[color:var(--ui-surface-3)] text-[color:var(--ui-text)]'
                      : isWeekend
                        ? 'text-[color:var(--ui-text-meta)]/60'
                        : 'text-[color:var(--ui-text-dim)]'
                )}
              >
                {day.getDate()}
              </span>
              <span className={cn('mt-0.5 text-[10px]', isWeekend ? 'text-[color:var(--ui-text-meta)]/45' : 'text-[color:var(--ui-text-meta)]/65')}>
                {MONTH_NAMES[day.getMonth()].slice(0, 3)}
              </span>
              {isTodayDay && !isSelected && (
                <div className="absolute bottom-1 h-1 w-1 rounded-full bg-[color:var(--ui-accent)]" />
              )}
            </button>
          )
        })}
        </div>
      </div>

      <div className="flex flex-1 overflow-y-auto">
        <div className="w-[60px] shrink-0 border-r border-[color:var(--ui-border-soft)]/50 bg-[color:var(--ui-bg)]">
          {hours.map(h => (
            <div
              key={h}
              style={{ height: HOUR_HEIGHT }}
              className="flex items-start justify-center pt-1.5"
            >
              <span className="font-meta text-[10px] font-medium text-[color:var(--ui-text-meta)]/70">{String(h).padStart(2, '0')}:00</span>
            </div>
          ))}
        </div>

        {weekDays.map((day, dayIdx) => {
          const key = toDateKey(day)
          const dayWeekdayIdx = dayIdx // 0=Seg, 6=Dom
          const daySchedules = (schedules ?? []).filter(
            s => s.day_of_week === dayWeekdayIdx && s.active
          )
          const dayReminders = (remindersByDay.get(key) ?? []).filter(r => !r.all_day)
          const isTodayDay = isToday(day)
          const isSelected = key === selectedDate
          const isWeekend = dayIdx >= 5

          return (
            <div
              key={key}
              onClick={() => onSelectDate(key)}
              style={{
                height: HOUR_HEIGHT * hours.length,
                ...(!isSelected && !isTodayDay ? timeGridStyle : {}),
              }}
              className={cn(
                'relative flex-1 cursor-pointer border-r border-[color:var(--ui-border-soft)]/40 transition-colors',
                isSelected && 'bg-[color:var(--ui-accent-soft)]/26',
                isTodayDay && !isSelected && 'bg-[color:var(--ui-surface-1)]/45',
                isWeekend && !isSelected && !isTodayDay && 'bg-[color:var(--ui-bg)]/65'
              )}
            >
              {(isSelected || isTodayDay) && hours.map(h => (
                <div
                  key={h}
                  style={{ top: (h - WEEK_START_HOUR) * HOUR_HEIGHT }}
                  className="absolute left-0 right-0 border-t border-[color:var(--ui-border-soft)]/35"
                />
              ))}

              {isTodayDay && nowMinutes >= WEEK_START_HOUR * 60 && nowMinutes <= WEEK_END_HOUR * 60 + 59 && (
                <div
                  style={{ top: nowTop }}
                  className="absolute left-0 right-0 z-20 flex items-center"
                >
                  <div className="h-2.5 w-2.5 rounded-full bg-[color:var(--ui-accent)] shadow-[0_0_8px_rgba(208,228,255,0.6)] -translate-x-1.5" />
                  <div className="h-px flex-1 bg-[color:var(--ui-accent)]/65 shadow-[0_0_8px_rgba(208,228,255,0.35)]" />
                </div>
              )}

              {daySchedules.map(s => {
                const startMin = timeToMinutes(s.start_time)
                const endMin = timeToMinutes(s.end_time)
                const top = minutesToTop(startMin)
                const height = durationToHeight(startMin, endMin)
                const colorIdx = scheduleColorMap.get(s.id) ?? 0
                const cls = EVENT_BG_COLORS[colorIdx]
                if (top < 0) return null
                return (
                  <div
                    key={`sched-${s.id}`}
                    onClick={e => {
                      e.stopPropagation()
                      onBlockClick({ kind: 'schedule', item: s, colorIdx, x: e.clientX + 8, y: e.clientY - 8 })
                    }}
                    style={{ top, height: Math.max(height, 24), left: 2, right: 2 }}
                    className={cn(
                      'absolute z-10 cursor-pointer overflow-hidden rounded-md border-l-[4px] px-2 py-1.5 transition-all duration-150 hover:scale-[1.01] hover:shadow-lg',
                      cls
                    )}
                  >
                    <p className="truncate text-[11px] font-semibold leading-tight">{s.title}</p>
                    <p className="mt-0.5 text-[10px] opacity-70 leading-tight">{s.start_time}–{s.end_time}</p>
                  </div>
                )
              })}

              {dayReminders.map((r) => {
                const startIso = r.starts_at
                const startMin = new Date(startIso).getHours() * 60 + new Date(startIso).getMinutes()
                const endIso = r.ends_at
                const endMin = endIso
                  ? new Date(endIso).getHours() * 60 + new Date(endIso).getMinutes()
                  : startMin + 30
                const top = minutesToTop(startMin)
                const height = durationToHeight(startMin, endMin)
                if (top < 0) return null
                return (
                  <div
                    key={`rem-${r.id}`}
                    onClick={e => {
                      e.stopPropagation()
                      onBlockClick({ kind: 'reminder', item: r, x: e.clientX + 8, y: e.clientY - 8 })
                    }}
                    style={{ top, height: Math.max(height, 24), left: 2, right: 2 }}
                    className="absolute z-10 cursor-pointer overflow-hidden rounded-md border-l-[4px] border-l-[color:var(--ui-accent)] bg-[color:var(--ui-accent-soft)] px-2 py-1.5 transition-all duration-150 hover:scale-[1.01]"
                  >
                    <p className="truncate text-[11px] font-semibold text-[color:var(--ui-accent)] leading-tight">{r.title}</p>
                    <p className="mt-0.5 text-[10px] text-[color:var(--ui-accent)]/70 leading-tight">{formatTime(r.starts_at)}</p>
                  </div>
                )
              })}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Componente principal ───────────────────────────────────────────────────
export function Schedule() {
  const qc = useQueryClient()
  const [monthCursor, setMonthCursor] = useState(() => startOfMonth(new Date()))
  const [selectedDate, setSelectedDate] = useState(() => toDateKey(new Date()))
  const [view, setView] = useState<'month' | 'week'>('month')
  const [selectedBlock, setSelectedBlock] = useState<SelectedBlock | null>(null)
  const [mobilePanel, setMobilePanel] = useState<'calendar' | 'detail'>('calendar')

  // Cursor de semana: segunda-feira da semana que contém selectedDate
  const weekCursor = useMemo(() => startOfWeek(new Date(`${selectedDate}T00:00:00`)), [selectedDate])

  const monthStart = useMemo(() => startOfMonth(monthCursor), [monthCursor])
  const monthEnd = useMemo(() => endOfMonth(monthCursor), [monthCursor])

  // Para view semanal, buscar lembretes da semana inteira
  const weekEnd = useMemo(() => {
    const d = new Date(weekCursor)
    d.setDate(d.getDate() + 6)
    d.setHours(23, 59, 59, 0)
    return d
  }, [weekCursor])

  // Form: lembrete
  const [reminderTitle, setReminderTitle] = useState('')
  const [reminderDate, setReminderDate] = useState(selectedDate)
  const [reminderStartTime, setReminderStartTime] = useState('09:00')
  const [reminderEndTime, setReminderEndTime] = useState('10:00')
  const [reminderNote, setReminderNote] = useState('')
  const [reminderAllDay, setReminderAllDay] = useState(false)

  // Form: bloco semanal
  const [scheduleTitle, setScheduleTitle] = useState('')
  const [scheduleDay, setScheduleDay] = useState<number>(
    new Date().getDay() === 0 ? 6 : new Date().getDay() - 1
  )
  const [scheduleStart, setScheduleStart] = useState('08:00')
  const [scheduleEnd, setScheduleEnd] = useState('09:00')
  const [scheduleNote, setScheduleNote] = useState('')

  // Query para vista mensal
  const { data: remindersMonth, isLoading: remindersLoadingMonth } = useQuery<ReminderItem[]>({
    queryKey: ['calendar-reminders', monthStart.toISOString(), monthEnd.toISOString()],
    queryFn: () =>
      apiClient.listReminders(
        `${monthStart.toISOString().slice(0, 10)}T00:00:00`,
        `${monthEnd.toISOString().slice(0, 10)}T23:59:59`
      ),
    retry: 1,
    enabled: view === 'month',
  })

  // Query para vista semanal
  const { data: remindersWeek, isLoading: remindersLoadingWeek } = useQuery<ReminderItem[]>({
    queryKey: ['calendar-reminders', weekCursor.toISOString(), weekEnd.toISOString()],
    queryFn: () =>
      apiClient.listReminders(
        `${toDateKey(weekCursor)}T00:00:00`,
        `${toDateKey(weekEnd)}T23:59:59`
      ),
    retry: 1,
    enabled: view === 'week',
  })

  const reminders = view === 'week' ? remindersWeek : remindersMonth
  const remindersLoading = view === 'week' ? remindersLoadingWeek : remindersLoadingMonth

  const { data: schedules, isLoading: schedulesLoading } = useQuery<ScheduleItem[]>({
    queryKey: ['calendar-schedules'],
    queryFn: () => apiClient.listSchedules(false),
    retry: 1,
  })

  const { data: overview } = useQuery<CalendarOverview>({
    queryKey: ['calendar-overview', selectedDate],
    queryFn: () => apiClient.getCalendarOverview(selectedDate),
    retry: 1,
  })

  const createReminder = useMutation({
    mutationFn: () =>
      apiClient.createReminder({
        title: reminderTitle,
        starts_at: reminderAllDay
          ? isoFromDateAndTime(reminderDate, '00:00')
          : isoFromDateAndTime(reminderDate, reminderStartTime),
        ends_at: reminderAllDay
          ? isoFromDateAndTime(reminderDate, '23:59')
          : isoFromDateAndTime(reminderDate, reminderEndTime),
        note: reminderNote || null,
        all_day: reminderAllDay,
      }),
    onSuccess: () => {
      toast.success('Lembrete salvo')
      setReminderTitle('')
      setReminderNote('')
      qc.invalidateQueries({ queryKey: ['calendar-reminders'] })
      qc.invalidateQueries({ queryKey: ['calendar-overview'] })
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao salvar lembrete'),
  })

  const removeReminder = useMutation({
    mutationFn: (id: number) => apiClient.deleteReminder(id),
    onSuccess: (_, id) => {
      toast.success('Lembrete removido')
      // Remove imediatamente do cache para evitar re-aparecer enquanto o refetch não chega
      qc.setQueriesData<ReminderItem[]>(
        { queryKey: ['calendar-reminders'] },
        old => old?.filter(r => r.id !== id),
      )
      qc.invalidateQueries({ queryKey: ['calendar-reminders'] })
      qc.invalidateQueries({ queryKey: ['calendar-overview'] })
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao remover'),
  })

  const createSchedule = useMutation({
    mutationFn: () =>
      apiClient.createSchedule({
        title: scheduleTitle,
        day_of_week: scheduleDay,
        start_time: scheduleStart,
        end_time: scheduleEnd,
        note: scheduleNote || null,
        active: true,
      }),
    onSuccess: () => {
      toast.success('Bloco fixo adicionado')
      setScheduleTitle('')
      setScheduleNote('')
      qc.invalidateQueries({ queryKey: ['calendar-schedules'] })
      qc.invalidateQueries({ queryKey: ['calendar-overview'] })
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao salvar'),
  })

  const removeSchedule = useMutation({
    mutationFn: (id: number) => apiClient.deleteSchedule(id),
    onSuccess: () => {
      toast.success('Bloco removido')
      setSelectedBlock(null)
      qc.invalidateQueries({ queryKey: ['calendar-schedules'] })
      qc.invalidateQueries({ queryKey: ['calendar-overview'] })
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao remover'),
  })

  const updateSchedule = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: { title: string; day_of_week: number; start_time: string; end_time: string; note?: string | null } }) =>
      apiClient.updateSchedule(id, { ...payload, active: true }),
    onSuccess: () => {
      toast.success('Bloco atualizado')
      setSelectedBlock(null)
      qc.invalidateQueries({ queryKey: ['calendar-schedules'] })
      qc.invalidateQueries({ queryKey: ['calendar-overview'] })
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao atualizar'),
  })

  const updateReminder = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: { title: string; starts_at: string; ends_at?: string | null; note?: string | null } }) =>
      apiClient.updateReminder(id, { ...payload, all_day: false }),
    onSuccess: () => {
      toast.success('Lembrete atualizado')
      setSelectedBlock(null)
      qc.invalidateQueries({ queryKey: ['calendar-reminders'] })
      qc.invalidateQueries({ queryKey: ['calendar-overview'] })
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao atualizar'),
  })

  const monthGrid = useMemo(() => buildMonthGrid(monthCursor), [monthCursor])

  const remindersByDay = useMemo(() => {
    const map = new Map<string, ReminderItem[]>()
    for (const r of reminders ?? []) {
      const key = toDateKey(new Date(r.starts_at))
      const bucket = map.get(key) ?? []
      bucket.push(r)
      map.set(key, bucket)
    }
    return map
  }, [reminders])

  const selectedWeekday = useMemo(() => {
    const d = new Date(`${selectedDate}T00:00:00`)
    const js = d.getDay()
    return js === 0 ? 6 : js - 1
  }, [selectedDate])

  const selectedDayReminders = useMemo(
    () => (remindersByDay.get(selectedDate) ?? []).sort((a, b) => a.starts_at.localeCompare(b.starts_at)),
    [remindersByDay, selectedDate]
  )

  const selectedDaySchedules = useMemo(
    () =>
      (schedules ?? [])
        .filter(item => item.day_of_week === selectedWeekday && item.active)
        .sort((a, b) => a.start_time.localeCompare(b.start_time)),
    [schedules, selectedWeekday]
  )

  const selectedDateObj = new Date(`${selectedDate}T00:00:00`)
  const selectedDateLabel = selectedDateObj.toLocaleDateString('pt-BR', {
    weekday: 'long', day: 'numeric', month: 'long',
  })

  // Label do header para view semanal
  const weekLabel = useMemo(() => {
    const weekEndDay = new Date(weekCursor)
    weekEndDay.setDate(weekCursor.getDate() + 6)
    const s = weekCursor
    const e = weekEndDay
    if (s.getMonth() === e.getMonth()) {
      return `${s.getDate()}–${e.getDate()} de ${MONTH_NAMES[s.getMonth()]} ${s.getFullYear()}`
    }
    return `${s.getDate()} ${MONTH_NAMES[s.getMonth()].slice(0, 3)} – ${e.getDate()} ${MONTH_NAMES[e.getMonth()].slice(0, 3)} ${e.getFullYear()}`
  }, [weekCursor])

  // Navegar semana: muda o selectedDate para a segunda da semana anterior/próxima
  function prevWeek() {
    const d = new Date(weekCursor)
    d.setDate(d.getDate() - 7)
    setSelectedDate(toDateKey(d))
    setMonthCursor(startOfMonth(d))
  }
  function nextWeek() {
    const d = new Date(weekCursor)
    d.setDate(d.getDate() + 7)
    setSelectedDate(toDateKey(d))
    setMonthCursor(startOfMonth(d))
  }

  function handleSelectDate(key: string) {
    setSelectedDate(key)
    setReminderDate(key)
    const d = new Date(`${key}T00:00:00`)
    setMonthCursor(startOfMonth(d))
    if (window.innerWidth < 768) setMobilePanel('detail')
  }

  return (
    <div className="relative flex h-[calc(100vh-4rem)] flex-col gap-0 overflow-hidden rounded-2xl border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-bg)] shadow-[0_24px_60px_rgba(0,0,0,0.42)] md:flex-row">
      {/* ── COLUNA ESQUERDA: Calendário ─────────────────────────────────────── */}
      <div className={`${mobilePanel === 'calendar' ? 'flex' : 'hidden'} md:flex flex-1 flex-col overflow-hidden`}>
        {/* Header do calendário */}
        <div className="flex items-center justify-between border-b border-[color:var(--ui-border-soft)]/70 bg-[color:var(--ui-bg)] px-3 py-3 sm:px-6 sm:py-4">
          <div className="flex items-center gap-2 sm:gap-4">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-[color:var(--ui-accent-soft)] sm:h-9 sm:w-9">
              <Calendar className="h-4 w-4 text-[color:var(--ui-accent)]" />
            </div>
            <div>
              <h1 className="font-headline text-base font-bold text-[color:var(--ui-text)] sm:text-xl">
                {view === 'week' ? weekLabel : `${MONTH_NAMES[monthCursor.getMonth()]} ${monthCursor.getFullYear()}`}
              </h1>
              <p className="app-kicker mt-0.5 hidden sm:block">Calendário pessoal</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 sm:gap-2">
            {/* Toggle view — semana só em telas maiores */}
            <div className="hidden rounded-lg border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-1)] p-0.5 sm:flex">
              <button
                onClick={() => setView('month')}
                className={cn(
                  'rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
                  view === 'month' ? 'bg-[color:var(--ui-surface-2)] text-[color:var(--ui-accent)]' : 'text-[color:var(--ui-text-meta)] hover:text-[color:var(--ui-text)]'
                )}
              >
                Mês
              </button>
              <button
                onClick={() => setView('week')}
                className={cn(
                  'rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
                  view === 'week' ? 'bg-[color:var(--ui-surface-2)] text-[color:var(--ui-accent)]' : 'text-[color:var(--ui-text-meta)] hover:text-[color:var(--ui-text)]'
                )}
              >
                Semana
              </button>
            </div>
            {/* Navegação */}
            <button
              onClick={() => {
                if (view === 'week') prevWeek()
                else setMonthCursor(new Date(monthCursor.getFullYear(), monthCursor.getMonth() - 1, 1))
              }}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-1)] text-[color:var(--ui-text-meta)] transition-colors hover:border-[color:var(--ui-border-strong)] hover:text-[color:var(--ui-text)]"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              onClick={() => {
                const now = new Date()
                setMonthCursor(startOfMonth(now))
                setSelectedDate(toDateKey(now))
              }}
              className="rounded-lg border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-1)] px-2.5 py-1.5 text-xs font-semibold text-[color:var(--ui-text-meta)] transition-colors hover:border-[color:var(--ui-border-strong)] hover:text-[color:var(--ui-text)] sm:px-3"
            >
              Hoje
            </button>
            <button
              onClick={() => {
                if (view === 'week') nextWeek()
                else setMonthCursor(new Date(monthCursor.getFullYear(), monthCursor.getMonth() + 1, 1))
              }}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-1)] text-[color:var(--ui-text-meta)] transition-colors hover:border-[color:var(--ui-border-strong)] hover:text-[color:var(--ui-text)]"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Conteúdo da view */}
        {view === 'month' ? (
          <div className="flex-1 overflow-auto p-3 pb-16 sm:p-5 md:pb-5">
            {/* Cabeçalho dos dias da semana */}
            <div className="mb-3 grid grid-cols-7">
              {WEEKDAY_LABELS.map((label, i) => (
                <div
                  key={label}
                  className={cn(
                    'py-2 text-center text-[10px] font-bold uppercase tracking-[0.14em]',
                    i >= 5 ? 'text-[color:var(--ui-text-meta)]/45' : 'text-[color:var(--ui-text-meta)]/70'
                  )}
                >
                  {label}
                </div>
              ))}
            </div>

            {/* Células mensais */}
            <div className="grid grid-cols-7 gap-px overflow-hidden rounded-2xl border border-[color:var(--ui-border-soft)]/55 bg-[color:var(--ui-border-soft)]/35">
              {monthGrid.map(cell => {
                const key = toDateKey(cell)
                const isCurrentMonth = cell.getMonth() === monthCursor.getMonth()
                const isSelected = key === selectedDate
                const isTodayCell = isToday(cell)
                const dayReminders = remindersByDay.get(key) ?? []
                const jsDay = cell.getDay()
                const weekday = jsDay === 0 ? 6 : jsDay - 1
                const daySchedules = (schedules ?? []).filter(s => s.day_of_week === weekday && s.active)

                return (
                  <button
                    key={key}
                    onClick={() => handleSelectDate(key)}
                    className={cn(
                      'group relative flex min-h-[64px] cursor-pointer flex-col p-1.5 text-left transition-all duration-150 sm:min-h-[132px] sm:p-3',
                      isSelected
                        ? 'bg-[color:var(--ui-accent-soft)] ring-1 ring-inset ring-[color:var(--ui-accent)]/45'
                        : isTodayCell
                          ? 'bg-[color:var(--ui-surface-1)] ring-1 ring-inset ring-[color:var(--ui-accent)]/28'
                          : 'bg-[color:var(--ui-surface-1)] hover:bg-[color:var(--ui-surface-2)]',
                      !isCurrentMonth && 'bg-[color:var(--ui-bg)]/65 opacity-60'
                    )}
                  >
                    <div className="mb-1.5 flex items-center justify-between">
                      <span
                        className={cn(
                          'flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold',
                          isTodayCell
                            ? 'bg-[color:var(--ui-accent)] text-[color:var(--ui-bg)]'
                            : isSelected
                              ? 'text-[color:var(--ui-accent)]'
                              : !isCurrentMonth
                                ? 'text-[color:var(--ui-text-meta)]/55'
                                : 'text-[color:var(--ui-text-dim)]'
                        )}
                      >
                        {cell.getDate()}
                      </span>
                      {(dayReminders.length + daySchedules.length) > 0 && (
                        <span className="text-[10px] font-medium text-[color:var(--ui-text-meta)]">
                          {dayReminders.length + daySchedules.length}
                        </span>
                      )}
                    </div>

                    {(() => {
                      const MAX_PILLS = window.innerWidth < 640 ? 1 : 4
                      type CellEvent = { key: string; title: string; colorIdx: number; durationMin: number }
                      const allEvents: CellEvent[] = [
                        ...daySchedules.map((s, i) => ({
                          key: `s-${s.id}`,
                          title: s.title,
                          colorIdx: i + 2,
                          durationMin: timeToMinutes(s.end_time) - timeToMinutes(s.start_time),
                        })),
                        ...dayReminders.map((r, i) => ({
                          key: `r-${r.id}`,
                          title: r.title,
                          colorIdx: i,
                          durationMin: r.ends_at
                            ? (new Date(r.ends_at).getTime() - new Date(r.starts_at).getTime()) / 60000
                            : 30,
                        })),
                      ].sort((a, b) => b.durationMin - a.durationMin)

                      const visible = allEvents.slice(0, MAX_PILLS)
                      const hidden = allEvents.length - visible.length

                      return (
                        <div className="flex flex-col gap-0.5 overflow-hidden">
                          {visible.map(ev => (
                            <EventPill key={ev.key} title={ev.title} colorIdx={ev.colorIdx} />
                          ))}
                          {hidden > 0 && (
                            <span className="mt-0.5 text-[10px] text-[color:var(--ui-text-meta)]">
                              +{hidden} mais
                            </span>
                          )}
                        </div>
                      )
                    })()}
                  </button>
                )
              })}
            </div>
          </div>
        ) : (
          <WeekView
            weekStart={weekCursor}
            reminders={remindersWeek}
            schedules={schedules}
            selectedDate={selectedDate}
            onSelectDate={handleSelectDate}
            onBlockClick={setSelectedBlock}
          />
        )}
      </div>

      {/* ── COLUNA DIREITA: Detalhes + Formulários ───────────────────────────── */}
      <div className={`${mobilePanel === 'detail' ? 'flex' : 'hidden'} md:flex w-full md:w-[380px] shrink-0 flex-col gap-0 overflow-hidden border-t md:border-t-0 border-l-0 md:border-l border-[color:var(--ui-border-soft)]/70 bg-[color:var(--ui-surface)]`}>
        {/* Cabeçalho do painel lateral */}
        <div className="border-b border-[color:var(--ui-border-soft)]/70 px-5 py-5">
          <p className="app-kicker">Selecionado</p>
          <p className="mt-1 font-headline text-base font-bold capitalize text-[color:var(--ui-text)]">{selectedDateLabel}</p>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 pb-16 pt-5 md:pb-5">
          {/* Resumo atual */}
          {overview && (overview.current_schedule_item || overview.next_schedule_item) && (
            <div className="rounded-2xl border border-emerald-500/25 bg-emerald-500/8 p-3.5">
              <div className="flex items-center gap-2 mb-2">
                <div className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(52,211,153,0.65)]" />
                <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-emerald-400">Agora</span>
              </div>
              {overview.current_schedule_item ? (
                <p className="text-sm text-[color:var(--ui-text)]">
                  {overview.current_schedule_item.title}
                  <span className="ml-1 text-xs text-[color:var(--ui-text-meta)]">
                    até {overview.current_schedule_item.end_time}
                  </span>
                </p>
              ) : overview.next_schedule_item ? (
                <p className="text-sm text-[color:var(--ui-text-dim)]">
                  Próximo: <span className="text-[color:var(--ui-text)]">{overview.next_schedule_item.title}</span>
                  <span className="ml-1 text-xs text-[color:var(--ui-text-meta)]">às {overview.next_schedule_item.start_time}</span>
                </p>
              ) : null}
            </div>
          )}

          {/* Lembretes do dia */}
          <div>
            <div className="mb-2 flex items-center gap-2">
              <Bell className="h-3.5 w-3.5 text-[color:var(--ui-accent)]" />
              <span className="app-kicker">Lembretes</span>
              {selectedDayReminders.length > 0 && (
                <Badge className="ml-auto h-4 border-[color:var(--ui-accent)]/35 bg-[color:var(--ui-accent-soft)] px-1.5 text-[10px] text-[color:var(--ui-accent)]">
                  {selectedDayReminders.length}
                </Badge>
              )}
            </div>
            {remindersLoading ? (
              <div className="space-y-2">
                {[1, 2].map(i => <Skeleton key={i} className="h-14 w-full rounded-xl bg-[color:var(--ui-surface-2)]" />)}
              </div>
            ) : selectedDayReminders.length === 0 ? (
              <p className="rounded-xl border border-dashed border-[color:var(--ui-border-soft)] py-4 text-center text-xs text-[color:var(--ui-text-meta)]">
                Nenhum lembrete neste dia
              </p>
            ) : (
              <div className="space-y-1.5">
                {selectedDayReminders.map(rem => (
                  <ReminderCard
                    key={rem.id}
                    reminder={rem}
                    onDelete={() => removeReminder.mutate(rem.id)}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Blocos fixos do dia */}
          <div>
            <div className="mb-2 flex items-center gap-2">
              <AlignJustify className="h-3.5 w-3.5 text-violet-400" />
              <span className="app-kicker">Cronograma fixo</span>
              <span className="ml-1 text-[10px] text-[color:var(--ui-text-meta)]">— {WEEKDAY_FULL[selectedWeekday]}</span>
            </div>
            {schedulesLoading ? (
              <div className="space-y-2">
                {[1].map(i => <Skeleton key={i} className="h-14 w-full rounded-xl bg-[color:var(--ui-surface-2)]" />)}
              </div>
            ) : selectedDaySchedules.length === 0 ? (
              <p className="rounded-xl border border-dashed border-[color:var(--ui-border-soft)] py-4 text-center text-xs text-[color:var(--ui-text-meta)]">
                Nenhum bloco para este dia
              </p>
            ) : (
              <div className="space-y-1.5">
                {selectedDaySchedules.map((item, i) => (
                  <ScheduleCard
                    key={item.id}
                    item={item}
                    colorIdx={i + 2}
                    onDelete={() => removeSchedule.mutate(item.id)}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Todos os blocos semanais */}
          {(schedules ?? []).length > 0 && (
            <div>
              <div className="mb-2 flex items-center gap-2">
                <Sparkles className="h-3.5 w-3.5 text-amber-400" />
                <span className="app-kicker">Todos os blocos semanais</span>
              </div>
              <div className="space-y-1.5">
                {(schedules ?? []).map((item, i) => (
                  <ScheduleCard
                    key={item.id}
                    item={item}
                    colorIdx={i + 2}
                    onDelete={() => removeSchedule.mutate(item.id)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Formulários */}
          <CollapsibleForm
            title="Novo lembrete"
            icon={<Bell className="h-3.5 w-3.5 text-[color:var(--ui-accent)]" />}
            color="bg-[color:var(--ui-accent-soft)]"
          >
            <Input
              placeholder="Título do lembrete"
              value={reminderTitle}
              onChange={e => setReminderTitle(e.target.value)}
              className="border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-3)] text-[color:var(--ui-text)] placeholder:text-[color:var(--ui-text-meta)]"
            />
            <Input
              type="date"
              value={reminderDate}
              onChange={e => setReminderDate(e.target.value)}
              className="border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-3)] text-[color:var(--ui-text)]"
            />
            {!reminderAllDay && (
              <div className="grid grid-cols-2 gap-2">
                <Input type="time" value={reminderStartTime} onChange={e => setReminderStartTime(e.target.value)} className="border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-3)] text-[color:var(--ui-text)]" />
                <Input type="time" value={reminderEndTime} onChange={e => setReminderEndTime(e.target.value)} className="border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-3)] text-[color:var(--ui-text)]" />
              </div>
            )}
            <Input
              placeholder="Observação (opcional)"
              value={reminderNote}
              onChange={e => setReminderNote(e.target.value)}
              className="border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-3)] text-[color:var(--ui-text)] placeholder:text-[color:var(--ui-text-meta)]"
            />
            <label className="flex cursor-pointer items-center gap-2 text-xs text-[color:var(--ui-text-dim)]">
              <div
                onClick={() => setReminderAllDay(v => !v)}
                className={cn(
                  'flex h-4 w-4 items-center justify-center rounded border transition-colors',
                  reminderAllDay
                    ? 'border-[color:var(--ui-accent)] bg-[color:var(--ui-accent)]'
                    : 'border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-3)]'
                )}
              >
                {reminderAllDay && <Check className="h-2.5 w-2.5 text-[color:var(--ui-bg)]" />}
              </div>
              Dia inteiro
            </label>
            <Button
              className="w-full bg-[color:var(--ui-accent)] text-[color:var(--ui-bg)] hover:bg-[color:var(--ui-accent-strong)]"
              onClick={() => createReminder.mutate()}
              disabled={!reminderTitle.trim() || createReminder.isPending}
            >
              {createReminder.isPending ? 'Salvando...' : 'Salvar lembrete'}
            </Button>
          </CollapsibleForm>

          <CollapsibleForm
            title="Novo bloco semanal"
            icon={<Clock className="h-3.5 w-3.5 text-violet-400" />}
            color="bg-violet-500/15"
          >
            <Input
              placeholder="Atividade fixa"
              value={scheduleTitle}
              onChange={e => setScheduleTitle(e.target.value)}
              className="border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-3)] text-[color:var(--ui-text)] placeholder:text-[color:var(--ui-text-meta)]"
            />
            <select
              value={scheduleDay}
              onChange={e => setScheduleDay(parseInt(e.target.value))}
              className="w-full rounded-md border border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-3)] px-3 py-2 text-sm text-[color:var(--ui-text)]"
            >
              {WEEKDAY_FULL.map((label, idx) => (
                <option key={label} value={idx}>{label}</option>
              ))}
            </select>
            <div className="grid grid-cols-2 gap-2">
              <Input type="time" value={scheduleStart} onChange={e => setScheduleStart(e.target.value)} className="border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-3)] text-[color:var(--ui-text)]" />
              <Input type="time" value={scheduleEnd} onChange={e => setScheduleEnd(e.target.value)} className="border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-3)] text-[color:var(--ui-text)]" />
            </div>
            <Input
              placeholder="Observação (opcional)"
              value={scheduleNote}
              onChange={e => setScheduleNote(e.target.value)}
              className="border-[color:var(--ui-border-strong)] bg-[color:var(--ui-surface-3)] text-[color:var(--ui-text)] placeholder:text-[color:var(--ui-text-meta)]"
            />
            <Button
              className="w-full bg-violet-600 text-white hover:bg-violet-700"
              onClick={() => createSchedule.mutate()}
              disabled={!scheduleTitle.trim() || createSchedule.isPending}
            >
              {createSchedule.isPending ? 'Salvando...' : 'Adicionar bloco'}
            </Button>
          </CollapsibleForm>
        </div>
      </div>

      {/* ── Mobile panel switcher ──────────────────────────────────────────── */}
      <div className="absolute bottom-0 left-0 right-0 flex border-t border-[color:var(--ui-border-soft)]/70 bg-[color:var(--ui-bg)] md:hidden">
        <button
          onClick={() => setMobilePanel('calendar')}
          className={cn(
            'flex flex-1 items-center justify-center gap-2 py-3 text-xs font-semibold transition-colors',
            mobilePanel === 'calendar'
              ? 'text-[color:var(--ui-accent)]'
              : 'text-[color:var(--ui-text-meta)]'
          )}
        >
          <Calendar className="h-4 w-4" />
          Calendário
        </button>
        <button
          onClick={() => setMobilePanel('detail')}
          className={cn(
            'flex flex-1 items-center justify-center gap-2 py-3 text-xs font-semibold transition-colors',
            mobilePanel === 'detail'
              ? 'text-[color:var(--ui-accent)]'
              : 'text-[color:var(--ui-text-meta)]'
          )}
        >
          <Bell className="h-4 w-4" />
          Detalhes
        </button>
      </div>

      {selectedBlock && (
        <BlockPopover
          block={selectedBlock}
          onClose={() => setSelectedBlock(null)}
          onDeleteSchedule={id => removeSchedule.mutate(id)}
          onDeleteReminder={id => removeReminder.mutate(id)}
          onUpdateSchedule={(id, payload) => updateSchedule.mutate({ id, payload })}
          onUpdateReminder={(id, payload) => updateReminder.mutate({ id, payload })}
        />
      )}
    </div>
  )
}
