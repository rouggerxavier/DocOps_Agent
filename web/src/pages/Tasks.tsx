import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Plus, Trash2, CheckCircle2, Circle, Clock, ChevronDown, ChevronUp,
  Flag, AlertTriangle, ListTodo, Pencil, Check, X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { apiClient, type TaskItem } from '@/api/client'
import { cn } from '@/lib/utils'

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
}: {
  task: TaskItem
  onStatusChange: (id: number, status: string) => void
  onEdit: (id: number, title: string, priority: string, due_date: string, status: string) => void
  onDelete: (id: number) => void
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
        <p className={cn(
          'text-sm font-medium text-zinc-100 leading-snug',
          isDone && 'line-through text-zinc-500',
        )}>
          {task.title}
        </p>
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

  const { data: tasks = [], isLoading } = useQuery<TaskItem[]>({
    queryKey: ['tasks'],
    queryFn: apiClient.listTasks,
  })

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
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100">Tarefas</h1>
          <p className="mt-0.5 text-sm text-zinc-500">
            {counts.doing > 0 ? `${counts.doing} em andamento · ` : ''}
            {counts.pending} pendentes
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
          />
        ))}
      </div>
    </div>
  )
}
