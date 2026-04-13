import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  CheckSquare,
  Circle,
  Clock3,
  ListTodo,
  Plus,
  Save,
  Sparkles,
  Square,
  Trash2,
  X,
} from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { PageShell } from '@/components/ui/page-shell'
import { apiClient, type TaskActivityLog, type TaskChecklistItem, type TaskItem } from '@/api/client'
import { cn } from '@/lib/utils'

type FilterTab = 'all' | 'doing' | 'pending' | 'done'

type BodyScrollLockState = {
  count: number
  overflow: string
}

type ScrollLockWindow = Window & {
  __docopsBodyScrollLockState?: BodyScrollLockState
}

type TaskStatus = 'pending' | 'doing' | 'done'

const STATUS_ORDER: Record<string, number> = {
  doing: 0,
  pending: 1,
  done: 2,
}

const FILTER_ORDER: FilterTab[] = ['all', 'doing', 'pending', 'done']

const FILTER_LABELS: Record<FilterTab, string> = {
  all: 'Todas',
  doing: 'Em andamento',
  pending: 'Pendentes',
  done: 'Concluidas',
}

const PRIORITY_LABELS: Record<string, string> = {
  high: 'Alta',
  normal: 'Media',
  low: 'Baixa',
}

function acquireBodyScrollLock() {
  const scrollLockWindow = window as ScrollLockWindow
  const state = scrollLockWindow.__docopsBodyScrollLockState ??= { count: 0, overflow: '' }

  if (state.count === 0) {
    state.overflow = document.body.style.overflow
  }

  state.count += 1
  document.body.style.overflow = 'hidden'

  return () => {
    const current = scrollLockWindow.__docopsBodyScrollLockState
    if (!current) return
    current.count = Math.max(0, current.count - 1)
    if (current.count === 0) {
      document.body.style.overflow = current.overflow
      current.overflow = ''
    }
  }
}

function toLocalDatetimeInput(iso: string | null) {
  if (!iso) return ''
  const date = new Date(iso)
  if (!Number.isFinite(date.getTime())) return ''
  const tzOffset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - tzOffset).toISOString().slice(0, 16)
}

function toIsoOrUndefined(localDatetime: string) {
  if (!localDatetime) return undefined
  const date = new Date(localDatetime)
  if (!Number.isFinite(date.getTime())) return undefined
  return date.toISOString()
}

function isOverdue(task: TaskItem) {
  if (!task.due_date || task.status === 'done') return false
  return new Date(task.due_date).getTime() < Date.now()
}

function formatDueShort(dueDate: string | null) {
  if (!dueDate) return 'Sem prazo'
  const date = new Date(dueDate)
  if (!Number.isFinite(date.getTime())) return 'Sem prazo'
  return date.toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function nextStatus(status: string): TaskStatus {
  if (status === 'pending') return 'doing'
  if (status === 'doing') return 'done'
  return 'pending'
}

function priorityBadgeClass(priority: string) {
  if (priority === 'high') return 'border-[#7f2f33] bg-[#3b181b] text-[#ffb4ab]'
  if (priority === 'normal') return 'border-[#2f4e6a] bg-[#142736] text-[#c5e3ff]'
  return 'border-[#41474e] bg-[#202426] text-[#c1c7cf]'
}

function statusLabel(status: string) {
  if (status === 'doing') return 'Em andamento'
  if (status === 'done') return 'Concluida'
  return 'Pendente'
}

function TaskPriorityBadge({ priority }: { priority: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-[0.08em]', priorityBadgeClass(priority))}>
      <span className={cn('h-1.5 w-1.5 rounded-full', priority === 'high' ? 'bg-[#ffb4ab]' : priority === 'normal' ? 'bg-[#c5e3ff]' : 'bg-[#8b9199]')} />
      Prioridade {PRIORITY_LABELS[priority] ?? priority}
    </span>
  )
}

function TaskCard({
  task,
  onOpen,
  onToggleStatus,
  onDelete,
  busy,
}: {
  task: TaskItem
  onOpen: () => void
  onToggleStatus: () => void
  onDelete: () => void
  busy: boolean
}) {
  const overdue = isOverdue(task)
  const done = task.status === 'done'
  const progress = task.checklist_total > 0 ? `${task.checklist_done}/${task.checklist_total}` : null

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onOpen()
        }
      }}
      className={cn(
        'group cursor-pointer rounded-2xl bg-[#1c1b1b] p-5 transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#90caf9]/50',
        'hover:bg-[#2a2a2a] hover:shadow-[0_20px_32px_rgba(0,0,0,0.32)]',
        done && 'opacity-75',
      )}
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <TaskPriorityBadge priority={task.priority} />
        <button
          type="button"
          onClick={event => {
            event.stopPropagation()
            onToggleStatus()
          }}
          className="inline-flex h-8 w-8 items-center justify-center rounded-full text-[#8b9199] transition-colors hover:bg-[#353534] hover:text-[#e5e2e1]"
          aria-label="Alterar status"
          disabled={busy}
        >
          {task.status === 'done' ? <CheckCircle2 className="h-4 w-4 text-[#8ad6a0]" /> : task.status === 'doing' ? <Clock3 className="h-4 w-4 text-[#c5e3ff]" /> : <Circle className="h-4 w-4" />}
        </button>
      </div>

      <h3 className={cn('font-headline text-xl font-bold tracking-tight text-[#e5e2e1]', done && 'line-through decoration-[#596068]')}>
        {task.title}
      </h3>
      {task.note ? <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-[#c1c7cf]">{task.note}</p> : null}

      <div className="mt-5 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-lg bg-[#0e0e0e] px-2.5 py-1 text-[11px] font-medium text-[#c1c7cf]">{statusLabel(task.status)}</span>
          {progress ? (
            <span className="inline-flex items-center gap-1 rounded-lg bg-[#0e0e0e] px-2.5 py-1 text-[11px] font-medium text-[#c1c7cf]">
              <CheckSquare className="h-3 w-3 text-[#90caf9]" />
              {progress}
            </span>
          ) : null}
        </div>

        <div className="flex items-center justify-between border-t border-[#41474e]/20 pt-3">
          <div className={cn('inline-flex items-center gap-1.5 text-xs font-semibold', overdue ? 'text-[#ffb4ab]' : 'text-[#aab2bc]')}>
            {overdue ? <AlertTriangle className="h-3.5 w-3.5" /> : <CalendarDays className="h-3.5 w-3.5" />}
            {formatDueShort(task.due_date)}
          </div>
          <button
            type="button"
            onClick={event => {
              event.stopPropagation()
              onDelete()
            }}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-[#8b9199] transition-colors hover:bg-[#3b1f1f] hover:text-[#ef9d9d]"
            disabled={busy}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Excluir
          </button>
        </div>
      </div>
    </article>
  )
}

function TaskDrawer({
  task,
  onClose,
}: {
  task: TaskItem
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [title, setTitle] = useState(task.title)
  const [note, setNote] = useState(task.note ?? '')
  const [priority, setPriority] = useState(task.priority)
  const [status, setStatus] = useState(task.status)
  const [due, setDue] = useState(toLocalDatetimeInput(task.due_date))
  const [newChecklist, setNewChecklist] = useState('')
  const [newActivity, setNewActivity] = useState('')

  useEffect(() => acquireBodyScrollLock(), [])

  useEffect(() => {
    setTitle(task.title)
    setNote(task.note ?? '')
    setPriority(task.priority)
    setStatus(task.status)
    setDue(toLocalDatetimeInput(task.due_date))
  }, [task.id, task.title, task.note, task.priority, task.status, task.due_date])

  const { data: checklist = [], isLoading: checklistLoading } = useQuery<TaskChecklistItem[]>({
    queryKey: ['task-checklist', task.id],
    queryFn: () => apiClient.listTaskChecklist(task.id),
  })

  const { data: activities = [], isLoading: activitiesLoading } = useQuery<TaskActivityLog[]>({
    queryKey: ['task-activities', task.id],
    queryFn: () => apiClient.listTaskActivities(task.id),
  })

  const updateTaskMut = useMutation({
    mutationFn: () =>
      apiClient.updateTask(task.id, title.trim(), note.trim() || undefined, status, priority, toIsoOrUndefined(due)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      toast.success('Tarefa atualizada.')
    },
    onError: () => toast.error('Erro ao atualizar tarefa.'),
  })

  const deleteTaskMut = useMutation({
    mutationFn: () => apiClient.deleteTask(task.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      toast.success('Tarefa excluida.')
      onClose()
    },
    onError: () => toast.error('Erro ao excluir tarefa.'),
  })

  const addChecklistMut = useMutation({
    mutationFn: (text: string) => apiClient.createChecklistItem(task.id, text),
    onSuccess: () => {
      setNewChecklist('')
      queryClient.invalidateQueries({ queryKey: ['task-checklist', task.id] })
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
    onError: () => toast.error('Erro ao adicionar checklist.'),
  })

  const toggleChecklistMut = useMutation({
    mutationFn: ({ itemId, done }: { itemId: number; done: boolean }) =>
      apiClient.updateChecklistItem(task.id, itemId, { done }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['task-checklist', task.id] })
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
    onError: () => toast.error('Erro ao atualizar checklist.'),
  })

  const deleteChecklistMut = useMutation({
    mutationFn: (itemId: number) => apiClient.deleteChecklistItem(task.id, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['task-checklist', task.id] })
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
    onError: () => toast.error('Erro ao excluir checklist.'),
  })

  const addActivityMut = useMutation({
    mutationFn: (text: string) => apiClient.createTaskActivity(task.id, text),
    onSuccess: () => {
      setNewActivity('')
      queryClient.invalidateQueries({ queryKey: ['task-activities', task.id] })
    },
    onError: () => toast.error('Erro ao registrar atividade.'),
  })

  const deleteActivityMut = useMutation({
    mutationFn: (activityId: number) => apiClient.deleteTaskActivity(task.id, activityId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['task-activities', task.id] }),
    onError: () => toast.error('Erro ao excluir atividade.'),
  })

  const doneChecklist = checklist.filter(item => item.done).length
  const checklistProgress = checklist.length > 0 ? Math.round((doneChecklist / checklist.length) * 100) : 0

  return (
    <div className="fixed inset-0 z-50 flex">
      <button type="button" className="flex-1 bg-black/60" onClick={onClose} aria-label="Fechar painel de tarefa" />
      <aside className="flex h-full w-full max-w-[520px] flex-col overflow-y-auto bg-[#131313] shadow-[0_0_0_1px_rgba(65,71,78,0.35),-30px_0_48px_rgba(0,0,0,0.45)]">
        <div className="sticky top-0 z-10 border-b border-[#41474e]/35 bg-[#131313]/95 px-5 py-4 backdrop-blur">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#8b9199]">Detalhes da tarefa</p>
            <button type="button" onClick={onClose} className="inline-flex h-8 w-8 items-center justify-center rounded-full text-[#8b9199] transition-colors hover:bg-[#2a2a2a] hover:text-[#e5e2e1]">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="grid gap-2">
            <Input value={title} onChange={event => setTitle(event.target.value)} className="border-[#41474e] bg-[#1c1b1b] text-[#e5e2e1]" placeholder="Titulo da tarefa" />
            <textarea
              value={note}
              onChange={event => setNote(event.target.value)}
              rows={3}
              className="w-full rounded-xl border border-[#41474e] bg-[#1c1b1b] px-3 py-2 text-sm text-[#e5e2e1] outline-none placeholder:text-[#8b9199] focus:border-[#90caf9]"
              placeholder="Observacao (opcional)"
            />
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <select value={priority} onChange={event => setPriority(event.target.value)} className="rounded-xl border border-[#41474e] bg-[#1c1b1b] px-3 py-2 text-sm text-[#e5e2e1] outline-none">
                <option value="high">Alta</option>
                <option value="normal">Media</option>
                <option value="low">Baixa</option>
              </select>
              <select value={status} onChange={event => setStatus(event.target.value)} className="rounded-xl border border-[#41474e] bg-[#1c1b1b] px-3 py-2 text-sm text-[#e5e2e1] outline-none">
                <option value="pending">Pendente</option>
                <option value="doing">Em andamento</option>
                <option value="done">Concluida</option>
              </select>
              <Input type="datetime-local" value={due} onChange={event => setDue(event.target.value)} className="border-[#41474e] bg-[#1c1b1b] text-[#e5e2e1]" />
            </div>
            <div className="flex items-center gap-2">
              <Button
                onClick={() => updateTaskMut.mutate()}
                disabled={!title.trim() || updateTaskMut.isPending}
                className="h-9 gap-1.5 rounded-lg border-0 bg-gradient-to-r from-[#c5e3ff] to-[#90caf9] text-[#03263b] hover:from-[#d6edff] hover:to-[#a6d4fb]"
              >
                <Save className="h-3.5 w-3.5" />
                Salvar
              </Button>
              <Button
                variant="outline"
                onClick={() => deleteTaskMut.mutate()}
                disabled={deleteTaskMut.isPending}
                className="h-9 border-[#7f2f33]/60 bg-[#2a1517] text-[#ffb4ab] hover:border-[#a0454a] hover:bg-[#3a1b1e]"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Excluir
              </Button>
            </div>
          </div>
        </div>

        <div className="space-y-5 p-5">
          <section className="rounded-2xl bg-[#1c1b1b] p-4">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-sm font-semibold text-[#e5e2e1]">Checklist</p>
              <span className="text-xs text-[#8b9199]">{doneChecklist}/{checklist.length}</span>
            </div>
            <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-[#0e0e0e]">
              <div className="h-full rounded-full bg-[#90caf9]" style={{ width: `${checklistProgress}%` }} />
            </div>

            <div className="mb-3 flex gap-2">
              <Input
                value={newChecklist}
                onChange={event => setNewChecklist(event.target.value)}
                onKeyDown={event => { if (event.key === 'Enter' && newChecklist.trim()) addChecklistMut.mutate(newChecklist.trim()) }}
                placeholder="Adicionar item..."
                className="h-9 border-[#41474e] bg-[#131313] text-[#e5e2e1]"
              />
              <Button
                size="sm"
                onClick={() => newChecklist.trim() && addChecklistMut.mutate(newChecklist.trim())}
                disabled={!newChecklist.trim() || addChecklistMut.isPending}
                className="h-9 rounded-lg border-0 bg-[#2a2a2a] px-3 text-[#e5e2e1] hover:bg-[#353534]"
              >
                <Plus className="h-3.5 w-3.5" />
              </Button>
            </div>

            {checklistLoading ? (
              <div className="space-y-2">
                {[1, 2].map(item => <div key={item} className="h-8 animate-pulse rounded-lg bg-[#2a2a2a]" />)}
              </div>
            ) : checklist.length === 0 ? (
              <p className="text-xs text-[#8b9199]">Sem itens no checklist.</p>
            ) : (
              <div className="space-y-1.5">
                {checklist.map(item => (
                  <div key={item.id} className="group flex items-center gap-2 rounded-lg bg-[#131313] px-2 py-1.5">
                    <button type="button" onClick={() => toggleChecklistMut.mutate({ itemId: item.id, done: !item.done })} className="text-[#8b9199] hover:text-[#c5e3ff]">
                      {item.done ? <CheckSquare className="h-4 w-4 text-[#8ad6a0]" /> : <Square className="h-4 w-4" />}
                    </button>
                    <span className={cn('flex-1 text-sm', item.done ? 'text-[#8b9199] line-through' : 'text-[#e5e2e1]')}>{item.text}</span>
                    <button type="button" onClick={() => deleteChecklistMut.mutate(item.id)} className="opacity-0 text-[#8b9199] transition-opacity hover:text-[#ef9d9d] group-hover:opacity-100">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="rounded-2xl bg-[#1c1b1b] p-4">
            <p className="mb-3 text-sm font-semibold text-[#e5e2e1]">Diario de progresso</p>
            <div className="mb-3 space-y-2">
              <textarea
                value={newActivity}
                onChange={event => setNewActivity(event.target.value)}
                rows={3}
                className="w-full rounded-xl border border-[#41474e] bg-[#131313] px-3 py-2 text-sm text-[#e5e2e1] outline-none placeholder:text-[#8b9199] focus:border-[#90caf9]"
                placeholder="Registre o que foi feito nesta tarefa..."
              />
              <Button
                onClick={() => newActivity.trim() && addActivityMut.mutate(newActivity.trim())}
                disabled={!newActivity.trim() || addActivityMut.isPending}
                className="h-9 rounded-lg border-0 bg-[#2a2a2a] text-[#e5e2e1] hover:bg-[#353534]"
              >
                Registrar atividade
              </Button>
            </div>

            {activitiesLoading ? (
              <div className="space-y-2">
                {[1, 2].map(item => <div key={item} className="h-14 animate-pulse rounded-lg bg-[#2a2a2a]" />)}
              </div>
            ) : activities.length === 0 ? (
              <p className="text-xs text-[#8b9199]">Nenhuma atividade registrada.</p>
            ) : (
              <div className="space-y-2">
                {activities.map(activity => (
                  <div key={activity.id} className="group rounded-lg bg-[#131313] px-3 py-2">
                    <p className="text-xs leading-relaxed text-[#c1c7cf] whitespace-pre-wrap">{activity.text}</p>
                    <div className="mt-1.5 flex items-center justify-between">
                      <span className="text-[10px] text-[#8b9199]">
                        {new Date(activity.created_at).toLocaleString('pt-BR', {
                          day: '2-digit',
                          month: 'short',
                          year: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                      <button type="button" onClick={() => deleteActivityMut.mutate(activity.id)} className="opacity-0 text-[#8b9199] transition-opacity hover:text-[#ef9d9d] group-hover:opacity-100">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </aside>
    </div>
  )
}

export function Tasks() {
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState<FilterTab>('all')
  const [drawerTaskId, setDrawerTaskId] = useState<number | null>(null)
  const [quickTitle, setQuickTitle] = useState('')
  const [quickPriority, setQuickPriority] = useState('normal')
  const [quickDue, setQuickDue] = useState('')

  const { data: tasks = [], isLoading } = useQuery<TaskItem[]>({
    queryKey: ['tasks'],
    queryFn: () => apiClient.listTasks(),
  })

  const createTaskMut = useMutation({
    mutationFn: ({ title, priority, dueDate }: { title: string; priority: string; dueDate: string }) =>
      apiClient.createTask(title, undefined, priority, toIsoOrUndefined(dueDate)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      setQuickTitle('')
      setQuickPriority('normal')
      setQuickDue('')
      toast.success('Tarefa criada.')
    },
    onError: () => toast.error('Erro ao criar tarefa.'),
  })

  const toggleStatusMut = useMutation({
    mutationFn: ({ id, status }: { id: number; status: TaskStatus }) => {
      const task = tasks.find(item => item.id === id)
      if (!task) throw new Error('Tarefa nao encontrada')
      return apiClient.updateTask(id, task.title, task.note ?? undefined, status, task.priority, task.due_date ?? undefined)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tasks'] }),
    onError: () => toast.error('Erro ao atualizar status da tarefa.'),
  })

  const deleteTaskMut = useMutation({
    mutationFn: (id: number) => apiClient.deleteTask(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      if (drawerTaskId === id) setDrawerTaskId(null)
      toast.success('Tarefa excluida.')
    },
    onError: () => toast.error('Erro ao excluir tarefa.'),
  })

  const counts = useMemo(() => ({
    all: tasks.length,
    doing: tasks.filter(task => task.status === 'doing').length,
    pending: tasks.filter(task => task.status === 'pending').length,
    done: tasks.filter(task => task.status === 'done').length,
  }), [tasks])

  const filteredTasks = useMemo(() => {
    return tasks
      .filter(task => filter === 'all' || task.status === filter)
      .sort((a, b) => {
        const statusDiff = (STATUS_ORDER[a.status] ?? 99) - (STATUS_ORDER[b.status] ?? 99)
        if (statusDiff !== 0) return statusDiff
        const priorityA = a.priority === 'high' ? 0 : a.priority === 'normal' ? 1 : 2
        const priorityB = b.priority === 'high' ? 0 : b.priority === 'normal' ? 1 : 2
        if (priorityA !== priorityB) return priorityA - priorityB
        return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
      })
  }, [tasks, filter])

  const activeTask = drawerTaskId == null ? null : tasks.find(task => task.id === drawerTaskId) ?? null
  const deletePendingId = deleteTaskMut.isPending ? deleteTaskMut.variables : null

  function submitQuickTask() {
    if (!quickTitle.trim()) return
    createTaskMut.mutate({
      title: quickTitle.trim(),
      priority: quickPriority,
      dueDate: quickDue,
    })
  }

  return (
    <>
      <PageShell className="relative space-y-6 overflow-hidden">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_82%_8%,rgba(144,202,249,0.16),transparent_44%),radial-gradient(circle_at_12%_18%,rgba(201,139,94,0.08),transparent_52%)]" />

        <header className="relative z-10 space-y-1">
          <h1 className="font-headline text-4xl font-extrabold tracking-tight text-[#e5e2e1]">Tarefas</h1>
          <p className="text-base text-[#c1c7cf]">Gerencie suas entregas e prazos com foco editorial.</p>
        </header>

        <section className="relative z-10 rounded-2xl bg-[#1c1b1b] p-2 shadow-[0_20px_36px_rgba(0,0,0,0.35)]">
          <div className="grid gap-2 md:grid-cols-[1fr_auto_auto_auto]">
            <div className="flex items-center gap-2 rounded-xl bg-[#0e0e0e] px-3">
              <Plus className="h-4 w-4 text-[#90caf9]" />
              <input
                value={quickTitle}
                onChange={event => setQuickTitle(event.target.value)}
                onKeyDown={event => { if (event.key === 'Enter') submitQuickTask() }}
                placeholder="Adicionar nova tarefa rapida..."
                className="h-11 w-full bg-transparent text-sm text-[#e5e2e1] outline-none placeholder:text-[#8b9199]"
              />
            </div>
            <select value={quickPriority} onChange={event => setQuickPriority(event.target.value)} className="h-11 rounded-xl border border-[#41474e] bg-[#131313] px-3 text-sm text-[#e5e2e1] outline-none">
              <option value="high">Alta</option>
              <option value="normal">Media</option>
              <option value="low">Baixa</option>
            </select>
            <Input type="datetime-local" value={quickDue} onChange={event => setQuickDue(event.target.value)} className="h-11 border-[#41474e] bg-[#131313] text-[#e5e2e1]" />
            <Button
              onClick={submitQuickTask}
              disabled={!quickTitle.trim() || createTaskMut.isPending}
              className="h-11 rounded-xl border-0 bg-gradient-to-r from-[#c5e3ff] to-[#90caf9] px-5 text-[#03263b] hover:from-[#d6edff] hover:to-[#a6d4fb]"
            >
              Criar
            </Button>
          </div>
        </section>

        <section className="relative z-10 flex flex-wrap gap-2">
          {FILTER_ORDER.map(item => (
            <button
              key={item}
              type="button"
              onClick={() => setFilter(item)}
              className={cn(
                'rounded-full px-5 py-2 text-sm font-semibold transition-colors',
                filter === item
                  ? 'bg-[#c5e3ff] text-[#00344f]'
                  : 'bg-[#2a2a2a] text-[#c1c7cf] hover:bg-[#3a3939] hover:text-[#e5e2e1]',
              )}
            >
              {FILTER_LABELS[item]} ({counts[item]})
            </button>
          ))}
        </section>

        <section className="relative z-10">
          {isLoading ? (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {[1, 2, 3, 4].map(item => <div key={item} className="h-52 animate-pulse rounded-2xl bg-[#2a2a2a]" />)}
            </div>
          ) : filteredTasks.length === 0 ? (
            <div className="flex min-h-[280px] flex-col items-center justify-center rounded-3xl bg-[#151515] px-6 text-center">
              <ListTodo className="mb-3 h-10 w-10 text-[#5f6770]" />
              <p className="font-headline text-2xl font-bold text-[#e5e2e1]">Tudo limpo por aqui</p>
              <p className="mt-1 max-w-md text-sm text-[#8b9199]">
                Nao encontramos tarefas para o filtro selecionado. Crie uma nova entrega para iniciar o proximo ciclo.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
              {filteredTasks.map(task => (
                <TaskCard
                  key={task.id}
                  task={task}
                  onOpen={() => setDrawerTaskId(task.id)}
                  onToggleStatus={() => toggleStatusMut.mutate({ id: task.id, status: nextStatus(task.status) })}
                  onDelete={() => deleteTaskMut.mutate(task.id)}
                  busy={deletePendingId === task.id || toggleStatusMut.isPending}
                />
              ))}
            </div>
          )}
        </section>

        <div className="relative z-10 rounded-2xl bg-[#1c1b1b] p-4">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-[#ffd9ae] shadow-[0_0_8px_rgba(255,217,174,0.7)] animate-pulse" />
            <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-[#ffd9ae]">Painel operacional ativo</span>
            <span className="ml-auto inline-flex items-center gap-1 text-[11px] text-[#8b9199]">
              <Sparkles className="h-3 w-3 text-[#c5e3ff]" />
              /api/tasks conectado
            </span>
          </div>
        </div>
      </PageShell>

      {activeTask && (
        <TaskDrawer
          task={activeTask}
          onClose={() => setDrawerTaskId(null)}
        />
      )}
    </>
  )
}
