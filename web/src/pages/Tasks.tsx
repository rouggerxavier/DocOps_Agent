import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Plus, Trash2, CheckCircle2, Circle, Clock, ChevronDown, ChevronUp,
  Flag, AlertTriangle, ListTodo, Pencil, Check, X, CheckSquare, Square,
  ScrollText,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PageShell } from '@/components/ui/page-shell'
import { apiClient, type TaskItem, type TaskChecklistItem, type TaskActivityLog } from '@/api/client'
import { cn } from '@/lib/utils'

type BodyScrollLockState = {
  count: number
  overflow: string
}

type ScrollLockWindow = Window & {
  __docopsBodyScrollLockState?: BodyScrollLockState
}

function acquireBodyScrollLock() {
  const scrollLockWindow = window as ScrollLockWindow
  const state = scrollLockWindow.__docopsBodyScrollLockState ??= {
    count: 0,
    overflow: '',
  }

  if (state.count === 0) {
    state.overflow = document.body.style.overflow
  }

  state.count += 1
  document.body.style.overflow = 'hidden'

  return () => {
    const currentState = scrollLockWindow.__docopsBodyScrollLockState

    if (!currentState) return

    currentState.count = Math.max(0, currentState.count - 1)

    if (currentState.count === 0) {
      document.body.style.overflow = currentState.overflow
      currentState.overflow = ''
    }
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const PRIORITY_STYLES: Record<string, string> = {
  high:   'text-red-400 border-red-800/50 bg-red-950/20',
  normal: 'text-zinc-400 border-zinc-700 bg-zinc-900',
  low:    'text-zinc-600 border-zinc-800 bg-zinc-900',
}

const STATUS_ORDER: Record<string, number> = { doing: 0, pending: 1, done: 2 }

function PriorityBadge({ priority }: { priority: string }) {
  const labels: Record<string, string> = { high: 'Alta', normal: 'Normal', low: 'Baixa' }
  return (
    <span className={cn(
      'inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-medium',
      PRIORITY_STYLES[priority] ?? PRIORITY_STYLES.normal,
    )}>
      <Flag className="h-2.5 w-2.5" />
      {labels[priority] ?? priority}
    </span>
  )
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { label: string; className: string }> = {
    pending: { label: 'Pendente',     className: 'text-zinc-400 border-zinc-700 bg-zinc-900' },
    doing:   { label: 'Em andamento', className: 'text-blue-400 border-blue-800/50 bg-blue-950/20' },
    done:    { label: 'Concluída',    className: 'text-emerald-400 border-emerald-800/50 bg-emerald-950/20' },
  }
  const { label, className } = config[status] ?? config.pending
  return (
    <span className={cn(
      'inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] font-medium',
      className,
    )}>
      {label}
    </span>
  )
}

// ── Task Drawer ───────────────────────────────────────────────────────────────

function TaskDrawer({ task, onClose }: { task: TaskItem; onClose: () => void }) {
  const qc = useQueryClient()
  const [newItem, setNewItem] = useState('')
  const [activityText, setActivityText] = useState('')

  useEffect(() => acquireBodyScrollLock(), [])

  const { data: checklist = [], isLoading: loadingChecklist } = useQuery<TaskChecklistItem[]>({
    queryKey: ['task-checklist', task.id],
    queryFn: () => apiClient.listTaskChecklist(task.id),
  })

  const { data: activities = [], isLoading: loadingActivities } = useQuery<TaskActivityLog[]>({
    queryKey: ['task-activities', task.id],
    queryFn: () => apiClient.listTaskActivities(task.id),
  })

  const addItemMut = useMutation({
    mutationFn: (text: string) => apiClient.createChecklistItem(task.id, text),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['task-checklist', task.id] })
      qc.invalidateQueries({ queryKey: ['tasks'] })
      setNewItem('')
    },
    onError: () => toast.error('Erro ao adicionar item.'),
  })

  const toggleItemMut = useMutation({
    mutationFn: ({ itemId, done }: { itemId: number; done: boolean }) =>
      apiClient.updateChecklistItem(task.id, itemId, { done }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['task-checklist', task.id] })
      qc.invalidateQueries({ queryKey: ['tasks'] })
    },
  })

  const deleteItemMut = useMutation({
    mutationFn: (itemId: number) => apiClient.deleteChecklistItem(task.id, itemId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['task-checklist', task.id] })
      qc.invalidateQueries({ queryKey: ['tasks'] })
    },
  })

  const addActivityMut = useMutation({
    mutationFn: (text: string) => apiClient.createTaskActivity(task.id, text),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['task-activities', task.id] })
      setActivityText('')
      toast.success('Progresso registrado!')
    },
    onError: () => toast.error('Erro ao registrar progresso.'),
  })

  const deleteActivityMut = useMutation({
    mutationFn: (logId: number) => apiClient.deleteTaskActivity(task.id, logId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['task-activities', task.id] }),
  })

  function submitItem() {
    if (!newItem.trim()) return
    addItemMut.mutate(newItem.trim())
  }

  function submitActivity() {
    if (!activityText.trim()) return
    addActivityMut.mutate(activityText.trim())
  }

  const doneCount = checklist.filter(i => i.done).length
  const totalCount = checklist.length
  const progressPct = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Overlay */}
      <div className="flex-1 bg-black/50" onClick={onClose} />

      {/* Panel */}
      <div className="w-[420px] bg-zinc-950 border-l border-zinc-800 flex flex-col overflow-y-auto">

        {/* Header */}
        <div className="sticky top-0 z-10 flex items-start gap-3 p-4 border-b border-zinc-800 bg-zinc-950">
          <div className="flex-1 min-w-0">
            <p className="text-[10px] text-zinc-600 uppercase tracking-widest mb-1">Detalhe da Tarefa</p>
            <h2 className="text-base font-semibold text-zinc-100 leading-snug">{task.title}</h2>
            <div className="mt-2 flex gap-1.5 flex-wrap">
              <PriorityBadge priority={task.priority} />
              <StatusBadge status={task.status} />
              {task.due_date && (
                <span className="inline-flex items-center gap-1 text-[10px] text-zinc-600">
                  <Clock className="h-2.5 w-2.5" />
                  {new Date(task.due_date).toLocaleDateString('pt-BR', {
                    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
                  })}
                </span>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="mt-0.5 shrink-0 rounded-lg p-1 text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Checklist section */}
        <div className="p-4 border-b border-zinc-800">
          <div className="flex items-center gap-2 mb-3">
            <CheckSquare className="h-4 w-4 text-blue-400" />
            <span className="text-sm font-medium text-zinc-200">Checklist de Metas</span>
            {totalCount > 0 && (
              <span className="text-xs text-zinc-500">{doneCount}/{totalCount}</span>
            )}
          </div>

          {/* Progress bar */}
          {totalCount > 0 && (
            <div className="mb-3">
              <div className="h-1.5 w-full rounded-full bg-zinc-800 overflow-hidden">
                <div
                  className={cn(
                    'h-full rounded-full transition-all duration-300',
                    progressPct === 100 ? 'bg-emerald-500' : 'bg-blue-500',
                  )}
                  style={{ width: `${progressPct}%` }}
                />
              </div>
              <p className="mt-1 text-[10px] text-zinc-600">{progressPct}% concluído</p>
            </div>
          )}

          {/* Items */}
          {loadingChecklist ? (
            <div className="space-y-2">
              {[1, 2].map(i => <div key={i} className="h-8 rounded-lg bg-zinc-900 animate-pulse" />)}
            </div>
          ) : (
            <div className="space-y-1">
              {checklist.map(item => (
                <div
                  key={item.id}
                  className="group flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-zinc-900 transition-colors"
                >
                  <button
                    onClick={() => toggleItemMut.mutate({ itemId: item.id, done: !item.done })}
                    className="shrink-0 text-zinc-500 hover:text-blue-400 transition-colors"
                  >
                    {item.done
                      ? <CheckSquare className="h-4 w-4 text-emerald-500" />
                      : <Square className="h-4 w-4" />
                    }
                  </button>
                  <span className={cn(
                    'flex-1 text-sm leading-snug',
                    item.done ? 'line-through text-zinc-600' : 'text-zinc-200',
                  )}>
                    {item.text}
                  </span>
                  <button
                    onClick={() => deleteItemMut.mutate(item.id)}
                    className="shrink-0 opacity-0 group-hover:opacity-100 text-zinc-700 hover:text-red-400 transition-all"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
              {checklist.length === 0 && (
                <p className="text-xs text-zinc-700 py-2 px-2">Nenhuma meta adicionada ainda.</p>
              )}
            </div>
          )}

          {/* Add item */}
          <div className="mt-2 flex gap-2">
            <Input
              value={newItem}
              onChange={e => setNewItem(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && submitItem()}
              placeholder="Adicionar meta..."
              className="flex-1 h-8 text-xs bg-zinc-900 border-zinc-800 focus:border-zinc-600"
            />
            <Button
              size="sm"
              variant="ghost"
              onClick={submitItem}
              disabled={!newItem.trim() || addItemMut.isPending}
              className="h-8 px-3 text-xs"
            >
              <Plus className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        {/* Activity log section */}
        <div className="p-4">
          <div className="flex items-center gap-2 mb-3">
            <ScrollText className="h-4 w-4 text-purple-400" />
            <span className="text-sm font-medium text-zinc-200">Diário de Progresso</span>
          </div>

          {/* Add activity */}
          <div className="space-y-2 mb-4">
            <textarea
              value={activityText}
              onChange={e => setActivityText(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submitActivity() }}
              placeholder="O que você fez nessa tarefa? (Ctrl+Enter para registrar)"
              rows={3}
              className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 outline-none resize-none focus:border-zinc-600 transition-colors"
            />
            <Button
              size="sm"
              onClick={submitActivity}
              disabled={!activityText.trim() || addActivityMut.isPending}
              className="w-full text-xs h-8"
            >
              Registrar progresso
            </Button>
          </div>

          {/* Activity list */}
          {loadingActivities ? (
            <div className="space-y-2">
              {[1, 2].map(i => <div key={i} className="h-14 rounded-lg bg-zinc-900 animate-pulse" />)}
            </div>
          ) : activities.length === 0 ? (
            <p className="text-center text-xs text-zinc-700 py-4">Nenhum progresso registrado ainda.</p>
          ) : (
            <div className="space-y-2">
              {activities.map(activity => (
                <div
                  key={activity.id}
                  className="group relative rounded-lg border border-zinc-800/50 bg-zinc-900/50 px-3 py-2.5"
                >
                  <p className="text-xs text-zinc-300 leading-relaxed pr-6 whitespace-pre-wrap">{activity.text}</p>
                  <p className="mt-1.5 text-[10px] text-zinc-700">
                    {new Date(activity.created_at).toLocaleString('pt-BR', {
                      day: '2-digit', month: 'short', year: 'numeric',
                      hour: '2-digit', minute: '2-digit',
                    })}
                  </p>
                  <button
                    onClick={() => deleteActivityMut.mutate(activity.id)}
                    className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-zinc-700 hover:text-red-400 transition-all"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Quick-add form ─────────────────────────────────────────────────────────────

function QuickAddForm({ onAdd }: { onAdd: (title: string, priority: string, due: string) => void }) {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [priority, setPriority] = useState('normal')
  const [due, setDue] = useState('')

  function submit() {
    if (!title.trim()) return
    onAdd(title.trim(), priority, due)
    setTitle('')
    setPriority('normal')
    setDue('')
    setOpen(false)
  }

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex w-full items-center gap-2 px-4 py-3 text-sm text-zinc-400 hover:text-zinc-100 transition-colors"
      >
        <Plus className="h-4 w-4 text-blue-400" />
        <span>Adicionar tarefa...</span>
        {open ? <ChevronUp className="ml-auto h-3.5 w-3.5" /> : <ChevronDown className="ml-auto h-3.5 w-3.5" />}
      </button>

      {open && (
        <div className="border-t border-zinc-800 p-4 space-y-3">
          <Input
            autoFocus
            value={title}
            onChange={e => setTitle(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && submit()}
            placeholder="Título da tarefa..."
            className="bg-zinc-800 border-zinc-700 text-sm"
          />
          <div className="flex gap-2">
            <div className="flex-1 space-y-1">
              <label className="text-xs text-zinc-500">Prioridade</label>
              <select
                value={priority}
                onChange={e => setPriority(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 py-1.5 text-xs text-zinc-200 outline-none"
              >
                <option value="low">Baixa</option>
                <option value="normal">Normal</option>
                <option value="high">Alta</option>
              </select>
            </div>
            <div className="flex-1 space-y-1">
              <label className="text-xs text-zinc-500">Prazo (opcional)</label>
              <Input
                type="datetime-local"
                value={due}
                onChange={e => setDue(e.target.value)}
                className="h-8 text-xs bg-zinc-800 border-zinc-700"
              />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <Button variant="ghost" size="sm" onClick={() => setOpen(false)} className="text-xs">Cancelar</Button>
            <Button size="sm" onClick={submit} disabled={!title.trim()} className="text-xs">Adicionar</Button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Task row ──────────────────────────────────────────────────────────────────

function TaskRow({
  task,
  onStatusChange,
  onEdit,
  onDelete,
  onOpenDrawer,
}: {
  task: TaskItem
  onStatusChange: (id: number, status: string) => void
  onEdit: (id: number, title: string, priority: string, due_date: string, status: string) => void
  onDelete: (id: number) => void
  onOpenDrawer: (id: number) => void
}) {
  const [editing, setEditing] = useState(false)
  const [editTitle, setEditTitle] = useState(task.title)
  const [editPriority, setEditPriority] = useState(task.priority)
  const [editStatus, setEditStatus] = useState(task.status)
  const [editDue, setEditDue] = useState(
    task.due_date ? new Date(task.due_date).toISOString().slice(0, 16) : '',
  )

  const isDone = task.status === 'done'
  const isDoing = task.status === 'doing'
  const isOverdue = task.due_date && !isDone && new Date(task.due_date) < new Date()
  const nextStatus = isDone ? 'pending' : isDoing ? 'done' : 'doing'

  function saveEdit() {
    if (!editTitle.trim()) return
    onEdit(task.id, editTitle.trim(), editPriority, editDue, editStatus)
    setEditing(false)
  }

  function cancelEdit() {
    setEditTitle(task.title)
    setEditPriority(task.priority)
    setEditStatus(task.status)
    setEditDue(task.due_date ? new Date(task.due_date).toISOString().slice(0, 16) : '')
    setEditing(false)
  }

  if (editing) {
    return (
      <div className="rounded-xl border border-blue-800/50 bg-zinc-900 px-4 py-3 space-y-3">
        <Input
          autoFocus
          value={editTitle}
          onChange={e => setEditTitle(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') saveEdit(); if (e.key === 'Escape') cancelEdit() }}
          className="bg-zinc-800 border-zinc-700 text-sm"
        />
        <div className="flex gap-2">
          <select
            value={editPriority}
            onChange={e => setEditPriority(e.target.value)}
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 py-1.5 text-xs text-zinc-200 outline-none"
          >
            <option value="low">Baixa</option>
            <option value="normal">Normal</option>
            <option value="high">Alta</option>
          </select>
          <select
            value={editStatus}
            onChange={e => setEditStatus(e.target.value)}
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 py-1.5 text-xs text-zinc-200 outline-none"
          >
            <option value="pending">Pendente</option>
            <option value="doing">Em andamento</option>
            <option value="done">Concluída</option>
          </select>
          <Input
            type="datetime-local"
            value={editDue}
            onChange={e => setEditDue(e.target.value)}
            className="flex-1 h-8 text-xs bg-zinc-800 border-zinc-700"
          />
        </div>
        <div className="flex gap-2 justify-end">
          <button onClick={cancelEdit} className="flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs text-zinc-500 hover:text-zinc-300">
            <X className="h-3 w-3" /> Cancelar
          </button>
          <button onClick={saveEdit} className="flex items-center gap-1 rounded-lg border border-emerald-800/50 bg-emerald-950/20 px-2.5 py-1.5 text-xs text-emerald-400 hover:bg-emerald-950/40">
            <Check className="h-3 w-3" /> Salvar
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className={cn(
      'group flex items-start gap-3 rounded-xl border px-4 py-3 transition-all',
      isDone
        ? 'border-zinc-800/50 bg-zinc-900/40 opacity-60'
        : 'border-zinc-800 bg-zinc-900 hover:border-zinc-700',
    )}>
      {/* Status toggle */}
      <button
        onClick={() => onStatusChange(task.id, nextStatus)}
        className="mt-0.5 shrink-0 text-zinc-500 hover:text-blue-400 transition-colors"
      >
        {isDone
          ? <CheckCircle2 className="h-5 w-5 text-emerald-500" />
          : isDoing
            ? <Clock className="h-5 w-5 text-blue-400 animate-pulse" />
            : <Circle className="h-5 w-5" />
        }
      </button>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <button
          onClick={() => onOpenDrawer(task.id)}
          className={cn(
            'text-left text-sm font-medium leading-snug hover:underline decoration-zinc-600 underline-offset-2 transition-colors',
            isDone ? 'line-through text-zinc-500' : 'text-zinc-100 hover:text-zinc-50',
          )}
        >
          {task.title}
        </button>
        {task.note && (
          <p className="mt-0.5 text-xs text-zinc-600 truncate">{task.note}</p>
        )}
        <div className="mt-1.5 flex items-center gap-2 flex-wrap">
          <PriorityBadge priority={task.priority} />
          {task.due_date && (
            <span className={cn(
              'inline-flex items-center gap-1 text-[10px]',
              isOverdue ? 'text-red-400' : 'text-zinc-600',
            )}>
              {isOverdue && <AlertTriangle className="h-2.5 w-2.5" />}
              <Clock className="h-2.5 w-2.5" />
              {new Date(task.due_date).toLocaleDateString('pt-BR', {
                day: '2-digit', month: 'short',
                hour: '2-digit', minute: '2-digit',
              })}
            </span>
          )}
          {isDoing && (
            <span className="inline-flex items-center gap-1 rounded-full border border-blue-800/50 bg-blue-950/20 px-1.5 py-0.5 text-[10px] text-blue-400">
              Em andamento
            </span>
          )}
          {/* Checklist progress badge */}
          {task.checklist_total > 0 && (
            <span className={cn(
              'inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-medium',
              task.checklist_done === task.checklist_total
                ? 'text-emerald-400 border-emerald-800/50 bg-emerald-950/20'
                : 'text-zinc-400 border-zinc-700 bg-zinc-900',
            )}>
              <CheckSquare className="h-2.5 w-2.5" />
              {task.checklist_done}/{task.checklist_total}
            </span>
          )}
        </div>
      </div>

      {/* Edit + Delete */}
      <div className="mt-0.5 flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-all">
        <button
          onClick={() => setEditing(true)}
          className="text-zinc-600 hover:text-blue-400 transition-colors"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={() => onDelete(task.id)}
          className="text-zinc-600 hover:text-red-400 transition-colors"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

type FilterTab = 'all' | 'pending' | 'doing' | 'done'

export function Tasks() {
  const qc = useQueryClient()
  const [filter, setFilter] = useState<FilterTab>('all')
  const [drawerTaskId, setDrawerTaskId] = useState<number | null>(null)

  const { data: tasks = [], isLoading } = useQuery<TaskItem[]>({
    queryKey: ['tasks'],
    queryFn: () => apiClient.listTasks(),
  })

  const drawerTask = drawerTaskId != null ? tasks.find(t => t.id === drawerTaskId) ?? null : null

  const createMut = useMutation({
    mutationFn: ({ title, priority, due_date }: { title: string; priority: string; due_date?: string }) =>
      apiClient.createTask(title, undefined, priority, due_date ? new Date(due_date).toISOString() : undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast.success('Tarefa criada!')
    },
    onError: () => toast.error('Erro ao criar tarefa.'),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) => {
      const task = tasks.find(t => t.id === id)!
      return apiClient.updateTask(id, task.title, task.note ?? undefined, status, task.priority, task.due_date ?? undefined)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }),
    onError: () => toast.error('Erro ao atualizar tarefa.'),
  })

  const editMut = useMutation({
    mutationFn: ({ id, title, priority, due_date, status }: { id: number; title: string; priority: string; due_date: string; status: string }) => {
      const task = tasks.find(t => t.id === id)!
      return apiClient.updateTask(id, title, task.note ?? undefined, status, priority, due_date ? new Date(due_date).toISOString() : undefined)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast.success('Tarefa atualizada.')
    },
    onError: () => toast.error('Erro ao atualizar tarefa.'),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => apiClient.deleteTask(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast.success('Tarefa excluída.')
    },
    onError: () => toast.error('Erro ao excluir tarefa.'),
  })

  const filtered = tasks
    .filter(t => filter === 'all' || t.status === filter)
    .sort((a, b) => {
      if (a.status !== b.status) return (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9)
      const pa = a.priority === 'high' ? 0 : a.priority === 'normal' ? 1 : 2
      const pb = b.priority === 'high' ? 0 : b.priority === 'normal' ? 1 : 2
      return pa - pb
    })

  const counts = {
    all: tasks.length,
    pending: tasks.filter(t => t.status === 'pending').length,
    doing: tasks.filter(t => t.status === 'doing').length,
    done: tasks.filter(t => t.status === 'done').length,
  }

  const tabs: { key: FilterTab; label: string }[] = [
    { key: 'all', label: `Todas (${counts.all})` },
    { key: 'doing', label: `Em andamento (${counts.doing})` },
    { key: 'pending', label: `Pendentes (${counts.pending})` },
    { key: 'done', label: `Concluídas (${counts.done})` },
  ]

  return (
    <>
      <PageShell className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-zinc-100">Tarefas</h1>
            <p className="mt-0.5 text-sm text-zinc-500">
              {isLoading
                ? 'Carregando...'
                : `${counts.doing > 0 ? `${counts.doing} em andamento · ` : ''}${counts.pending} pendentes`}
            </p>
          </div>
        </div>

        {/* Quick add */}
        <QuickAddForm
          onAdd={(title, priority, due) =>
            createMut.mutate({ title, priority, due_date: due || undefined })
          }
        />

        {/* Tabs */}
        <div className="flex gap-1 border-b border-zinc-800">
          {tabs.map(tab => (
            <button
              key={tab.key}
              onClick={() => setFilter(tab.key)}
              className={cn(
                'px-3 py-2 text-xs font-medium transition-colors',
                filter === tab.key
                  ? 'border-b-2 border-blue-500 text-blue-400'
                  : 'text-zinc-500 hover:text-zinc-300',
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Task list */}
        {isLoading && (
          <div className="space-y-2">
            {[1, 2, 3].map(i => <div key={i} className="h-16 rounded-xl bg-zinc-900 animate-pulse" />)}
          </div>
        )}

        {!isLoading && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <ListTodo className="h-10 w-10 text-zinc-800 mb-3" />
            <p className="text-sm text-zinc-600">
              {filter === 'all' ? 'Nenhuma tarefa ainda.' : `Nenhuma tarefa ${filter === 'done' ? 'concluída' : filter === 'doing' ? 'em andamento' : 'pendente'}.`}
            </p>
          </div>
        )}

        <div className="space-y-2">
          {filtered.map(task => (
            <TaskRow
              key={task.id}
              task={task}
              onStatusChange={(id, status) => updateMut.mutate({ id, status })}
              onEdit={(id, title, priority, due_date, status) => editMut.mutate({ id, title, priority, due_date, status })}
              onDelete={id => deleteMut.mutate(id)}
              onOpenDrawer={id => setDrawerTaskId(id)}
            />
          ))}
        </div>
      </PageShell>

      {/* Task drawer */}
      {drawerTask && (
        <TaskDrawer
          task={drawerTask}
          onClose={() => setDrawerTaskId(null)}
        />
      )}
    </>
  )
}
