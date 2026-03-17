import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Plus, Pin, PinOff, Trash2, FileText, Search, Save, X, StickyNote,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { apiClient, type NoteItem } from '@/api/client'
import { cn } from '@/lib/utils'

// ── Markdown preview simples ──────────────────────────────────────────────────

function MarkdownPreview({ text }: { text: string }) {
  if (!text.trim()) return <p className="text-xs text-zinc-600 italic">Sem conteúdo...</p>
  // Render first 3 lines as preview
  const lines = text.split('\n').filter(l => l.trim()).slice(0, 3)
  return (
    <div className="space-y-0.5">
      {lines.map((line, i) => (
        <p key={i} className="text-xs text-zinc-400 truncate leading-relaxed">
          {line.replace(/^#{1,6}\s/, '').replace(/\*\*(.*?)\*\*/g, '$1').replace(/`(.*?)`/g, '$1')}
        </p>
      ))}
    </div>
  )
}

// ── Editor de nota ────────────────────────────────────────────────────────────

function NoteEditor({
  note,
  onSave,
  onClose,
}: {
  note: NoteItem | null
  onSave: (title: string, content: string, pinned: boolean) => void
  onClose: () => void
}) {
  const [title, setTitle] = useState(note?.title ?? '')
  const [content, setContent] = useState(note?.content ?? '')
  const [pinned, setPinned] = useState(note?.pinned ?? false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  const hasChanges =
    title !== (note?.title ?? '') ||
    content !== (note?.content ?? '') ||
    pinned !== (note?.pinned ?? false)

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-2 border-b border-zinc-800 px-4 py-3">
        <input
          value={title}
          onChange={e => setTitle(e.target.value)}
          placeholder="Título da nota..."
          className="flex-1 bg-transparent text-base font-semibold text-zinc-100 placeholder:text-zinc-600 outline-none"
        />
        <button
          onClick={() => setPinned(p => !p)}
          className={cn(
            'rounded-lg p-1.5 transition-colors',
            pinned ? 'text-yellow-400 hover:text-yellow-300' : 'text-zinc-600 hover:text-zinc-400',
          )}
          title={pinned ? 'Desafixar' : 'Fixar'}
        >
          {pinned ? <Pin className="h-4 w-4" /> : <PinOff className="h-4 w-4" />}
        </button>
        <Button
          size="sm"
          onClick={() => onSave(title, content, pinned)}
          disabled={!title.trim() || !hasChanges}
          className="h-7 text-xs gap-1"
        >
          <Save className="h-3.5 w-3.5" /> Salvar
        </Button>
        <button
          onClick={onClose}
          className="rounded-lg p-1.5 text-zinc-600 hover:text-zinc-300 transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Markdown editor */}
      <div className="flex flex-1 overflow-hidden">
        <textarea
          ref={textareaRef}
          value={content}
          onChange={e => setContent(e.target.value)}
          placeholder={"Escreva em Markdown...\n\n# Título\n**negrito**, *itálico*, `código`\n- item de lista"}
          className="flex-1 resize-none bg-transparent p-4 text-sm text-zinc-200 placeholder:text-zinc-700 outline-none font-mono leading-relaxed"
          style={{ userSelect: 'text' }}
        />
      </div>

      {/* Word count */}
      <div className="border-t border-zinc-800 px-4 py-2 text-xs text-zinc-700">
        {content.trim().split(/\s+/).filter(Boolean).length} palavras · {content.length} caracteres
      </div>
    </div>
  )
}

// ── Card de nota ──────────────────────────────────────────────────────────────

function NoteCard({
  note,
  active,
  onClick,
  onDelete,
}: {
  note: NoteItem
  active: boolean
  onClick: () => void
  onDelete: () => void
}) {
  return (
    <div
      onClick={onClick}
      className={cn(
        'group relative cursor-pointer rounded-xl border p-3.5 transition-all',
        active
          ? 'border-blue-600/60 bg-blue-950/20'
          : 'border-zinc-800 bg-zinc-900 hover:border-zinc-700',
      )}
    >
      {note.pinned && (
        <Pin className="absolute top-2.5 right-2.5 h-3 w-3 text-yellow-500" />
      )}
      <p className="text-sm font-semibold text-zinc-100 pr-5 truncate">{note.title}</p>
      <div className="mt-1.5">
        <MarkdownPreview text={note.content} />
      </div>
      <p className="mt-2 text-[10px] text-zinc-700">
        {new Date(note.updated_at).toLocaleDateString('pt-BR', {
          day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
        })}
      </p>
      <button
        onClick={e => { e.stopPropagation(); onDelete() }}
        className="absolute bottom-2.5 right-2.5 opacity-0 group-hover:opacity-100 rounded p-0.5 text-zinc-600 hover:text-red-400 transition-all"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export function Notes() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [activeId, setActiveId] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)

  const { data: notes = [], isLoading } = useQuery<NoteItem[]>({
    queryKey: ['notes'],
    queryFn: apiClient.listNotes,
  })

  const createMut = useMutation({
    mutationFn: ({ title, content, pinned }: { title: string; content: string; pinned: boolean }) =>
      apiClient.createNote(title, content, pinned),
    onSuccess: note => {
      qc.invalidateQueries({ queryKey: ['notes'] })
      setCreating(false)
      setActiveId(note.id)
      toast.success('Nota criada!')
    },
    onError: () => toast.error('Erro ao criar nota.'),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, title, content, pinned }: { id: number; title: string; content: string; pinned: boolean }) =>
      apiClient.updateNote(id, title, content, pinned),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notes'] })
      toast.success('Nota salva!')
    },
    onError: () => toast.error('Erro ao salvar nota.'),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => apiClient.deleteNote(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notes'] })
      toast.success('Nota excluída.')
      if (activeId !== null) setActiveId(null)
    },
    onError: () => toast.error('Erro ao excluir nota.'),
  })

  const filtered = notes.filter(n =>
    n.title.toLowerCase().includes(search.toLowerCase()) ||
    n.content.toLowerCase().includes(search.toLowerCase()),
  )

  const activeNote = notes.find(n => n.id === activeId) ?? null

  function handleSave(title: string, content: string, pinned: boolean) {
    if (creating) {
      createMut.mutate({ title, content, pinned })
    } else if (activeNote) {
      updateMut.mutate({ id: activeNote.id, title, content, pinned })
    }
  }

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar de notas */}
      <aside className="flex w-72 flex-col border-r border-zinc-800 bg-zinc-950">
        {/* Header */}
        <div className="border-b border-zinc-800 px-4 py-4">
          <div className="flex items-center justify-between mb-3">
            <h1 className="text-sm font-semibold text-zinc-100">Notas</h1>
            <Button
              size="sm"
              onClick={() => { setCreating(true); setActiveId(null) }}
              className="h-7 text-xs gap-1"
            >
              <Plus className="h-3.5 w-3.5" /> Nova
            </Button>
          </div>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-600" />
            <Input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Buscar notas..."
              className="h-8 pl-8 text-xs bg-zinc-900 border-zinc-800"
            />
          </div>
        </div>

        {/* Lista */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {isLoading && (
            <div className="space-y-2">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-20 rounded-xl bg-zinc-900 animate-pulse" />
              ))}
            </div>
          )}
          {!isLoading && filtered.length === 0 && (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <StickyNote className="h-8 w-8 text-zinc-700 mb-2" />
              <p className="text-xs text-zinc-600">
                {search ? 'Nenhuma nota encontrada.' : 'Nenhuma nota ainda.\nCrie sua primeira nota!'}
              </p>
            </div>
          )}
          {filtered.map(note => (
            <NoteCard
              key={note.id}
              note={note}
              active={activeId === note.id && !creating}
              onClick={() => { setActiveId(note.id); setCreating(false) }}
              onDelete={() => deleteMut.mutate(note.id)}
            />
          ))}
        </div>

        {/* Footer */}
        <div className="border-t border-zinc-800 px-4 py-2">
          <p className="text-xs text-zinc-700">{notes.length} {notes.length === 1 ? 'nota' : 'notas'}</p>
        </div>
      </aside>

      {/* Editor */}
      <main className="flex flex-1 flex-col bg-zinc-950">
        {(creating || activeNote) ? (
          <NoteEditor
            key={creating ? 'new' : activeNote?.id}
            note={creating ? null : activeNote}
            onSave={handleSave}
            onClose={() => { setCreating(false); setActiveId(null) }}
          />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center text-center">
            <FileText className="h-12 w-12 text-zinc-800 mb-3" />
            <p className="text-sm text-zinc-600">Selecione uma nota ou crie uma nova</p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCreating(true)}
              className="mt-4 text-xs gap-1 border-zinc-700 text-zinc-400 hover:text-zinc-100"
            >
              <Plus className="h-3.5 w-3.5" /> Nova nota
            </Button>
          </div>
        )}
      </main>
    </div>
  )
}
