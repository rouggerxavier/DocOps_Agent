import { useMemo, useState, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CalendarDays, Clock, Plus, Trash2, Sparkles, ChevronLeft, ChevronRight,
  Bell, AlignJustify, Calendar, Check, X
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
  'bg-blue-500/20 text-blue-300 border-blue-500/30',
  'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  'bg-violet-500/20 text-violet-300 border-violet-500/30',
  'bg-amber-500/20 text-amber-300 border-amber-500/30',
  'bg-rose-500/20 text-rose-300 border-rose-500/30',
  'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
]

const EVENT_BG_COLORS = [
  'bg-blue-500/15 border-blue-500/40 text-blue-200',
  'bg-emerald-500/15 border-emerald-500/40 text-emerald-200',
  'bg-violet-500/15 border-violet-500/40 text-violet-200',
  'bg-amber-500/15 border-amber-500/40 text-amber-200',
  'bg-rose-500/15 border-rose-500/40 text-rose-200',
  'bg-cyan-500/15 border-cyan-500/40 text-cyan-200',
]

// Hora de início do grid semanal (6h da manhã)
const WEEK_START_HOUR = 6
// Hora de fim do grid semanal (23h)
const WEEK_END_HOUR = 23
// Altura em pixels por hora
const HOUR_HEIGHT = 56

function toDateKey(d: Date) {
  return d.toISOString().slice(0, 10)
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
    <div className={cn('truncate rounded px-1.5 py-0.5 text-[10px] font-medium border', cls)}>
      {title}
    </div>
  )
}

// ── Card de lembrete na lista lateral ──────────────────────────────────────
function ReminderCard({ reminder, onDelete }: { reminder: ReminderItem; onDelete: () => void }) {
  return (
    <div className="group flex items-start gap-3 rounded-xl border border-zinc-800/60 bg-zinc-900/60 p-3 transition-all hover:border-zinc-700">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-500/15">
        <Bell className="h-3.5 w-3.5 text-blue-400" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="truncate text-sm font-medium text-zinc-200">{reminder.title}</p>
        <p className="text-xs text-zinc-500">
          {reminder.all_day ? 'Dia inteiro' : formatTime(reminder.starts_at)}
          {reminder.note ? ` · ${reminder.note}` : ''}
        </p>
      </div>
      <button
        onClick={onDelete}
        className="shrink-0 text-zinc-600 opacity-0 transition-opacity hover:text-red-400 group-hover:opacity-100"
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
    <div className="group flex items-start gap-3 rounded-xl border border-zinc-800/60 bg-zinc-900/60 p-3 transition-all hover:border-zinc-700">
      <div className={cn('mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border', cls)}>
        <Clock className="h-3.5 w-3.5" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="truncate text-sm font-medium text-zinc-200">{item.title}</p>
        <p className="text-xs text-zinc-500">
          {item.start_time} – {item.end_time}
          {item.note ? ` · ${item.note}` : ''}
        </p>
      </div>
      <button
        onClick={onDelete}
        className="shrink-0 text-zinc-600 opacity-0 transition-opacity hover:text-red-400 group-hover:opacity-100"
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
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-zinc-800/40"
      >
        <div className={cn('flex h-7 w-7 shrink-0 items-center justify-center rounded-full', color)}>
          {icon}
        </div>
        <span className="flex-1 text-sm font-semibold text-zinc-200">{title}</span>
        <Plus className={cn('h-4 w-4 text-zinc-500 transition-transform', open && 'rotate-45')} />
      </button>
      {open && (
        <div className="border-t border-zinc-800/60 px-4 pb-4 pt-3 space-y-3">
          {children}
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
}: {
  weekStart: Date
  reminders: ReminderItem[] | undefined
  schedules: ScheduleItem[] | undefined
  selectedDate: string
  onSelectDate: (key: string) => void
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
      const key = new Date(r.starts_at).toISOString().slice(0, 10)
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
  const todayKey = toDateKey(now)

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Cabeçalho dos dias */}
      <div className="flex border-b border-zinc-800 bg-zinc-950">
        {/* espaço para a coluna de horas */}
        <div className="w-14 shrink-0" />
        {weekDays.map((day, i) => {
          const key = toDateKey(day)
          const isSelected = key === selectedDate
          const isTodayDay = isToday(day)
          return (
            <button
              key={key}
              onClick={() => onSelectDate(key)}
              className={cn(
                'flex flex-1 flex-col items-center py-3 transition-colors hover:bg-zinc-800/30',
                isSelected && 'bg-zinc-800/50',
              )}
            >
              <span className="text-[11px] font-semibold uppercase tracking-widest text-zinc-500">
                {WEEKDAY_LABELS[i]}
              </span>
              <span
                className={cn(
                  'mt-1 flex h-7 w-7 items-center justify-center rounded-full text-sm font-bold',
                  isTodayDay ? 'bg-blue-600 text-white' : isSelected ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-300'
                )}
              >
                {day.getDate()}
              </span>
              <span className="text-[10px] text-zinc-600">
                {MONTH_NAMES[day.getMonth()].slice(0, 3)}
              </span>
            </button>
          )
        })}
      </div>

      {/* Grade de horas */}
      <div className="flex flex-1 overflow-y-auto">
        {/* Coluna de horas */}
        <div className="w-14 shrink-0 border-r border-zinc-800 bg-zinc-950/50">
          {hours.map(h => (
            <div
              key={h}
              style={{ height: HOUR_HEIGHT }}
              className="flex items-start justify-end pr-2 pt-1"
            >
              <span className="text-[10px] font-medium text-zinc-600">{h}h</span>
            </div>
          ))}
        </div>

        {/* Colunas dos dias */}
        {weekDays.map((day, dayIdx) => {
          const key = toDateKey(day)
          const dayWeekdayIdx = dayIdx // 0=Seg, 6=Dom
          const daySchedules = (schedules ?? []).filter(
            s => s.day_of_week === dayWeekdayIdx && s.active
          )
          const dayReminders = (remindersByDay.get(key) ?? []).filter(r => !r.all_day)
          const isTodayDay = isToday(day)
          const isSelected = key === selectedDate

          return (
            <div
              key={key}
              onClick={() => onSelectDate(key)}
              style={{ height: HOUR_HEIGHT * hours.length }}
              className={cn(
                'relative flex-1 cursor-pointer border-r border-zinc-800/60',
                isSelected && 'bg-blue-500/5',
                isTodayDay && !isSelected && 'bg-zinc-900/30',
              )}
            >
              {/* Linhas de hora */}
              {hours.map(h => (
                <div
                  key={h}
                  style={{ top: (h - WEEK_START_HOUR) * HOUR_HEIGHT }}
                  className="absolute left-0 right-0 border-t border-zinc-800/40"
                />
              ))}

              {/* Linha do horário atual (só no dia de hoje) */}
              {isTodayDay && nowMinutes >= WEEK_START_HOUR * 60 && nowMinutes <= WEEK_END_HOUR * 60 + 59 && (
                <div
                  style={{ top: nowTop }}
                  className="absolute left-0 right-0 z-20 flex items-center"
                >
                  <div className="h-2 w-2 rounded-full bg-red-500 -translate-x-1" />
                  <div className="h-px flex-1 bg-red-500/70" />
                </div>
              )}

              {/* Blocos fixos do cronograma */}
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
                    onClick={e => e.stopPropagation()}
                    style={{ top, height: Math.max(height, 24), left: 2, right: 2 }}
                    className={cn(
                      'absolute z-10 rounded-md border px-1.5 py-1 overflow-hidden',
                      cls
                    )}
                  >
                    <p className="truncate text-[11px] font-semibold leading-tight">{s.title}</p>
                    <p className="text-[10px] opacity-70 leading-tight">{s.start_time}–{s.end_time}</p>
                  </div>
                )
              })}

              {/* Lembretes */}
              {dayReminders.map((r, i) => {
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
                    onClick={e => e.stopPropagation()}
                    style={{ top, height: Math.max(height, 24), left: 2, right: 2 }}
                    className="absolute z-10 rounded-md border border-blue-500/50 bg-blue-500/20 px-1.5 py-1 overflow-hidden"
                  >
                    <p className="truncate text-[11px] font-semibold text-blue-200 leading-tight">{r.title}</p>
                    <p className="text-[10px] text-blue-300/70 leading-tight">{formatTime(r.starts_at)}</p>
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
    onSuccess: () => {
      toast.success('Lembrete removido')
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
      qc.invalidateQueries({ queryKey: ['calendar-schedules'] })
      qc.invalidateQueries({ queryKey: ['calendar-overview'] })
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao remover'),
  })

  const monthGrid = useMemo(() => buildMonthGrid(monthCursor), [monthCursor])

  const remindersByDay = useMemo(() => {
    const map = new Map<string, ReminderItem[]>()
    for (const r of reminders ?? []) {
      const key = new Date(r.starts_at).toISOString().slice(0, 10)
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
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] gap-0 overflow-hidden">
      {/* ── COLUNA ESQUERDA: Calendário ─────────────────────────────────────── */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header do calendário */}
        <div className="flex items-center justify-between border-b border-zinc-800 bg-zinc-950 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-600/20">
              <Calendar className="h-4 w-4 text-blue-400" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-zinc-100">
                {view === 'week' ? weekLabel : `${MONTH_NAMES[monthCursor.getMonth()]} ${monthCursor.getFullYear()}`}
              </h1>
              <p className="text-xs text-zinc-500">Calendário pessoal</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* Toggle view */}
            <div className="flex rounded-lg border border-zinc-800 bg-zinc-900 p-0.5">
              <button
                onClick={() => setView('month')}
                className={cn(
                  'rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                  view === 'month' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
                )}
              >
                Mês
              </button>
              <button
                onClick={() => setView('week')}
                className={cn(
                  'rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                  view === 'week' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
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
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900 text-zinc-400 transition-colors hover:border-zinc-700 hover:text-zinc-200"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              onClick={() => {
                const now = new Date()
                setMonthCursor(startOfMonth(now))
                setSelectedDate(toDateKey(now))
              }}
              className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-400 transition-colors hover:border-zinc-700 hover:text-zinc-200"
            >
              Hoje
            </button>
            <button
              onClick={() => {
                if (view === 'week') nextWeek()
                else setMonthCursor(new Date(monthCursor.getFullYear(), monthCursor.getMonth() + 1, 1))
              }}
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900 text-zinc-400 transition-colors hover:border-zinc-700 hover:text-zinc-200"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Conteúdo da view */}
        {view === 'month' ? (
          <div className="flex-1 overflow-auto p-3">
            {/* Cabeçalho dos dias da semana */}
            <div className="mb-2 grid grid-cols-7 gap-1">
              {WEEKDAY_LABELS.map(label => (
                <div key={label} className="py-2 text-center text-[11px] font-semibold uppercase tracking-widest text-zinc-600">
                  {label}
                </div>
              ))}
            </div>

            {/* Células mensais */}
            <div className="grid grid-cols-7 gap-1">
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
                      'group relative flex min-h-[90px] flex-col rounded-xl border p-2 text-left transition-all duration-150',
                      isSelected
                        ? 'border-blue-500/60 bg-blue-500/10 ring-1 ring-blue-500/30'
                        : isTodayCell
                          ? 'border-zinc-700 bg-zinc-900 hover:border-zinc-600'
                          : 'border-zinc-800/60 bg-zinc-900/30 hover:border-zinc-700 hover:bg-zinc-900/60',
                      !isCurrentMonth && 'opacity-30'
                    )}
                  >
                    <div className="mb-1.5 flex items-center justify-between">
                      <span
                        className={cn(
                          'flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold',
                          isTodayCell
                            ? 'bg-blue-600 text-white'
                            : isSelected
                              ? 'text-blue-300'
                              : 'text-zinc-400'
                        )}
                      >
                        {cell.getDate()}
                      </span>
                      {(dayReminders.length + daySchedules.length) > 0 && (
                        <span className="text-[10px] font-medium text-zinc-600">
                          {dayReminders.length + daySchedules.length}
                        </span>
                      )}
                    </div>

                    <div className="flex flex-col gap-0.5 overflow-hidden">
                      {daySchedules.slice(0, 1).map((s, i) => (
                        <EventPill key={`s-${s.id}`} title={s.title} colorIdx={i + 2} />
                      ))}
                      {dayReminders.slice(0, 2).map((r, i) => (
                        <EventPill key={`r-${r.id}`} title={r.title} colorIdx={i} />
                      ))}
                      {(dayReminders.length + daySchedules.length) > 3 && (
                        <span className="text-[10px] text-zinc-600">
                          +{dayReminders.length + daySchedules.length - 3} mais
                        </span>
                      )}
                    </div>
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
          />
        )}
      </div>

      {/* ── COLUNA DIREITA: Detalhes + Formulários ───────────────────────────── */}
      <div className="flex w-80 shrink-0 flex-col gap-0 overflow-hidden border-l border-zinc-800">
        {/* Cabeçalho do painel lateral */}
        <div className="border-b border-zinc-800 bg-zinc-950 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-zinc-500">Selecionado</p>
          <p className="mt-0.5 text-sm font-semibold capitalize text-zinc-200">{selectedDateLabel}</p>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4">
          {/* Resumo atual */}
          {overview && (overview.current_schedule_item || overview.next_schedule_item) && (
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3">
              <div className="flex items-center gap-2 mb-2">
                <div className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-xs font-semibold text-emerald-400">Agora</span>
              </div>
              {overview.current_schedule_item ? (
                <p className="text-sm text-zinc-200">
                  {overview.current_schedule_item.title}
                  <span className="ml-1 text-xs text-zinc-500">
                    até {overview.current_schedule_item.end_time}
                  </span>
                </p>
              ) : overview.next_schedule_item ? (
                <p className="text-sm text-zinc-400">
                  Próximo: <span className="text-zinc-200">{overview.next_schedule_item.title}</span>
                  <span className="ml-1 text-xs text-zinc-500">às {overview.next_schedule_item.start_time}</span>
                </p>
              ) : null}
            </div>
          )}

          {/* Lembretes do dia */}
          <div>
            <div className="mb-2 flex items-center gap-2">
              <Bell className="h-3.5 w-3.5 text-blue-400" />
              <span className="text-xs font-semibold text-zinc-400">Lembretes</span>
              {selectedDayReminders.length > 0 && (
                <Badge className="ml-auto h-4 bg-blue-600/20 px-1.5 text-[10px] text-blue-300 border-blue-600/30">
                  {selectedDayReminders.length}
                </Badge>
              )}
            </div>
            {remindersLoading ? (
              <div className="space-y-2">
                {[1, 2].map(i => <Skeleton key={i} className="h-14 w-full rounded-xl" />)}
              </div>
            ) : selectedDayReminders.length === 0 ? (
              <p className="rounded-xl border border-dashed border-zinc-800 py-4 text-center text-xs text-zinc-600">
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
              <span className="text-xs font-semibold text-zinc-400">Cronograma fixo</span>
              <span className="ml-1 text-xs text-zinc-600">— {WEEKDAY_FULL[selectedWeekday]}</span>
            </div>
            {schedulesLoading ? (
              <div className="space-y-2">
                {[1].map(i => <Skeleton key={i} className="h-14 w-full rounded-xl" />)}
              </div>
            ) : selectedDaySchedules.length === 0 ? (
              <p className="rounded-xl border border-dashed border-zinc-800 py-4 text-center text-xs text-zinc-600">
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
                <span className="text-xs font-semibold text-zinc-400">Todos os blocos semanais</span>
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
            icon={<Bell className="h-3.5 w-3.5 text-blue-400" />}
            color="bg-blue-500/15"
          >
            <Input
              placeholder="Título do lembrete"
              value={reminderTitle}
              onChange={e => setReminderTitle(e.target.value)}
              className="bg-zinc-800/60 border-zinc-700"
            />
            <Input
              type="date"
              value={reminderDate}
              onChange={e => setReminderDate(e.target.value)}
              className="bg-zinc-800/60 border-zinc-700"
            />
            {!reminderAllDay && (
              <div className="grid grid-cols-2 gap-2">
                <Input type="time" value={reminderStartTime} onChange={e => setReminderStartTime(e.target.value)} className="bg-zinc-800/60 border-zinc-700" />
                <Input type="time" value={reminderEndTime} onChange={e => setReminderEndTime(e.target.value)} className="bg-zinc-800/60 border-zinc-700" />
              </div>
            )}
            <Input
              placeholder="Observação (opcional)"
              value={reminderNote}
              onChange={e => setReminderNote(e.target.value)}
              className="bg-zinc-800/60 border-zinc-700"
            />
            <label className="flex cursor-pointer items-center gap-2 text-xs text-zinc-400">
              <div
                onClick={() => setReminderAllDay(v => !v)}
                className={cn(
                  'flex h-4 w-4 items-center justify-center rounded border transition-colors',
                  reminderAllDay ? 'border-blue-500 bg-blue-600' : 'border-zinc-600 bg-zinc-800'
                )}
              >
                {reminderAllDay && <Check className="h-2.5 w-2.5 text-white" />}
              </div>
              Dia inteiro
            </label>
            <Button
              className="w-full"
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
              className="bg-zinc-800/60 border-zinc-700"
            />
            <select
              value={scheduleDay}
              onChange={e => setScheduleDay(parseInt(e.target.value))}
              className="w-full rounded-md border border-zinc-700 bg-zinc-800/60 px-3 py-2 text-sm text-zinc-100"
            >
              {WEEKDAY_FULL.map((label, idx) => (
                <option key={label} value={idx}>{label}</option>
              ))}
            </select>
            <div className="grid grid-cols-2 gap-2">
              <Input type="time" value={scheduleStart} onChange={e => setScheduleStart(e.target.value)} className="bg-zinc-800/60 border-zinc-700" />
              <Input type="time" value={scheduleEnd} onChange={e => setScheduleEnd(e.target.value)} className="bg-zinc-800/60 border-zinc-700" />
            </div>
            <Input
              placeholder="Observação (opcional)"
              value={scheduleNote}
              onChange={e => setScheduleNote(e.target.value)}
              className="bg-zinc-800/60 border-zinc-700"
            />
            <Button
              className="w-full"
              onClick={() => createSchedule.mutate()}
              disabled={!scheduleTitle.trim() || createSchedule.isPending}
            >
              {createSchedule.isPending ? 'Salvando...' : 'Adicionar bloco'}
            </Button>
          </CollapsibleForm>
        </div>
      </div>
    </div>
  )
}
