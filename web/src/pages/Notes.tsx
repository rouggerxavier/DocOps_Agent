import { useDeferredValue, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import { toast } from 'sonner'
import {
  BookText,
  Clock3,
  Eye,
  EyeOff,
  Pin,
  PinOff,
  Plus,
  Save,
  Search,
  Sparkles,
  StickyNote,
  Trash2,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { apiClient, type NoteItem } from '@/api/client'
import { cn } from '@/lib/utils'

function formatRelativeTimestamp(value: string) {
  const timestamp = new Date(value).getTime()
  if (!Number.isFinite(timestamp)) return '--'

  const diffMs = Date.now() - timestamp
  const minutes = Math.max(0, Math.floor(diffMs / 60_000))
  if (minutes < 1) return 'agora'
  if (minutes < 60) return `${minutes} min`

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} h`

  const days = Math.floor(hours / 24)
  if (days < 7) return `${days} d`

  return new Date(value).toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: 'short',
  })
}

function formatPreciseTimestamp(value: string) {
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return '--'
  return date.toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function NotePreview({ content }: { content: string }) {
  const compact = content.replace(/\s+/g, ' ').trim()
  if (!compact) {
    return <p className="text-xs text-[#8c8f94] italic">Sem conteudo...</p>
  }

  const stripped = compact
    .replace(/[`*_>#-]/g, '')
    .replace(/\[(.*?)\]\((.*?)\)/g, '$1')
    .trim()
  const excerpt = stripped.slice(0, 170)

  return (
    <p className="text-sm leading-relaxed text-[#c1c7cf]">
      {excerpt}
      {stripped.length > excerpt.length ? '...' : ''}
    </p>
  )
}

function NoteListCard({
  note,
  active,
  onSelect,
  onDelete,
  deleting,
}: {
  note: NoteItem
  active: boolean
  onSelect: () => void
  onDelete: () => void
  deleting: boolean
}) {
  return (
    <article
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onSelect()
        }
      }}
      className={cn(
        'group cursor-pointer rounded-2xl px-5 py-4 transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#90caf9]/60',
        active
          ? 'bg-[#2a2a2a] shadow-[inset_3px_0_0_0_#90caf9,0_18px_32px_rgba(0,0,0,0.35)]'
          : 'bg-[#1c1b1b] hover:bg-[#262626]',
      )}
      aria-label={`Abrir nota ${note.title}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="mb-2 flex items-center gap-2">
            {note.pinned && <Pin className="h-3.5 w-3.5 shrink-0 text-[#ffd9ae]" />}
            <h3 className={cn('truncate font-headline text-base font-bold tracking-tight', active ? 'text-[#c5e3ff]' : 'text-[#e5e2e1]')}>
              {note.title}
            </h3>
          </div>
          <NotePreview content={note.content} />
        </div>

        <div className="flex shrink-0 flex-col items-end gap-2">
          <span className="rounded-full bg-[#353534] px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#aab2bc]">
            {formatRelativeTimestamp(note.updated_at)}
          </span>
          <button
            type="button"
            onClick={event => {
              event.stopPropagation()
              onDelete()
            }}
            disabled={deleting}
            className="inline-flex h-7 w-7 items-center justify-center rounded-full text-[#7f8791] opacity-0 transition-all hover:bg-[#3b1f1f] hover:text-[#ef9d9d] focus-visible:opacity-100 group-hover:opacity-100 disabled:opacity-60"
            aria-label={`Excluir nota ${note.title}`}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </article>
  )
}

function NoteEditorPanel({
  note,
  creating,
  onSave,
  onClose,
  saving,
}: {
  note: NoteItem | null
  creating: boolean
  onSave: (title: string, content: string, pinned: boolean) => void
  onClose: () => void
  saving: boolean
}) {
  const [title, setTitle] = useState(note?.title ?? '')
  const [content, setContent] = useState(note?.content ?? '')
  const [pinned, setPinned] = useState(note?.pinned ?? false)
  const [showPreview, setShowPreview] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    setTitle(note?.title ?? '')
    setContent(note?.content ?? '')
    setPinned(note?.pinned ?? false)
    setShowPreview(false)
  }, [note?.id, note?.title, note?.content, note?.pinned])

  useEffect(() => {
    textareaRef.current?.focus()
  }, [note?.id, creating])

  const baseTitle = note?.title ?? ''
  const baseContent = note?.content ?? ''
  const basePinned = note?.pinned ?? false

  const hasChanges = creating
    ? Boolean(title.trim() || content.trim() || pinned)
    : title !== baseTitle || content !== baseContent || pinned !== basePinned
  const canSave = title.trim().length > 0 && hasChanges && !saving
  const words = content.trim() ? content.trim().split(/\s+/).length : 0

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden rounded-3xl bg-[#0f0f0f] shadow-[0_20px_44px_rgba(0,0,0,0.38)]">
      <div className="flex items-center gap-2 bg-[#1a1a1a] px-4 py-3 md:px-6">
        <input
          value={title}
          onChange={event => setTitle(event.target.value)}
          placeholder="Titulo da nota..."
          className="flex-1 bg-transparent text-base font-semibold text-[#e5e2e1] outline-none placeholder:text-[#7f8791]"
        />

        <button
          type="button"
          onClick={() => setPinned(value => !value)}
          className={cn(
            'inline-flex h-8 w-8 items-center justify-center rounded-full transition-colors',
            pinned ? 'bg-[#3d3220] text-[#ffd9ae]' : 'text-[#8b9199] hover:bg-[#2a2a2a] hover:text-[#e5e2e1]',
          )}
          aria-label={pinned ? 'Desafixar nota' : 'Fixar nota'}
          title={pinned ? 'Desafixar nota' : 'Fixar nota'}
        >
          {pinned ? <Pin className="h-4 w-4" /> : <PinOff className="h-4 w-4" />}
        </button>

        <button
          type="button"
          onClick={() => setShowPreview(value => !value)}
          className={cn(
            'inline-flex h-8 w-8 items-center justify-center rounded-full transition-colors',
            showPreview ? 'bg-[#203142] text-[#c5e3ff]' : 'text-[#8b9199] hover:bg-[#2a2a2a] hover:text-[#e5e2e1]',
          )}
          aria-label={showPreview ? 'Ocultar preview markdown' : 'Mostrar preview markdown'}
          title={showPreview ? 'Ocultar preview markdown' : 'Mostrar preview markdown'}
        >
          {showPreview ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>

        <Button
          size="sm"
          onClick={() => onSave(title.trim(), content, pinned)}
          disabled={!canSave}
          className="h-8 gap-1.5 rounded-lg border-0 bg-gradient-to-r from-[#c5e3ff] to-[#90caf9] px-3 text-[#03263b] shadow-[0_8px_20px_rgba(144,202,249,0.28)] hover:from-[#d2ebff] hover:to-[#a9d5fa]"
        >
          <Save className="h-3.5 w-3.5" />
          Salvar
        </Button>

        <button
          type="button"
          onClick={onClose}
          className="inline-flex h-8 w-8 items-center justify-center rounded-full text-[#8b9199] transition-colors hover:bg-[#2a2a2a] hover:text-[#e5e2e1]"
          aria-label="Fechar editor"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex min-h-0 flex-1">
        <textarea
          ref={textareaRef}
          value={content}
          onChange={event => setContent(event.target.value)}
          placeholder={'Escreva em markdown...\n\n# Titulo\n- itens\n- referencias'}
          className={cn(
            'min-h-0 resize-none bg-[#121212] p-4 text-sm leading-relaxed text-[#e5e2e1] outline-none placeholder:text-[#6f7781] md:p-6',
            showPreview ? 'w-1/2' : 'w-full',
          )}
        />

        {showPreview && (
          <div className="w-1/2 overflow-y-auto bg-[#181818] p-4 md:p-6">
            {content.trim() ? (
              <div className="prose prose-invert prose-sm max-w-none prose-headings:text-[#e5e2e1] prose-p:text-[#c1c7cf] prose-strong:text-[#e5e2e1] prose-li:text-[#c1c7cf] prose-code:text-[#9ecfff]">
                <ReactMarkdown>{content}</ReactMarkdown>
              </div>
            ) : (
              <p className="text-sm italic text-[#8b9199]">Nada para visualizar.</p>
            )}
          </div>
        )}
      </div>

      <div className="bg-[#1a1a1a] px-4 py-2 text-xs text-[#8b9199] md:px-6">
        {words} palavras · {content.length} caracteres
      </div>
    </section>
  )
}

export function Notes() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [activeId, setActiveId] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)

  const deferredSearch = useDeferredValue(search)

  const { data: notes = [], isLoading } = useQuery<NoteItem[]>({
    queryKey: ['notes'],
    queryFn: apiClient.listNotes,
  })

  useEffect(() => {
    if (notes.length === 0) {
      setActiveId(null)
      return
    }
    if (activeId !== null && notes.some(note => note.id === activeId)) return
    if (activeId !== null) setActiveId(null)
  }, [notes, activeId])

  const createMutation = useMutation({
    mutationFn: ({ title, content, pinned }: { title: string; content: string; pinned: boolean }) =>
      apiClient.createNote(title, content, pinned),
    onSuccess: note => {
      queryClient.invalidateQueries({ queryKey: ['notes'] })
      setCreating(false)
      setActiveId(note.id)
      toast.success('Nota criada.')
    },
    onError: () => toast.error('Erro ao criar nota.'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, title, content, pinned }: { id: number; title: string; content: string; pinned: boolean }) =>
      apiClient.updateNote(id, title, content, pinned),
    onSuccess: note => {
      queryClient.invalidateQueries({ queryKey: ['notes'] })
      setActiveId(note.id)
      toast.success('Nota salva.')
    },
    onError: () => toast.error('Erro ao salvar nota.'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => apiClient.deleteNote(id),
    onSuccess: (_, deletedId) => {
      queryClient.invalidateQueries({ queryKey: ['notes'] })
      if (activeId === deletedId) {
        setActiveId(null)
        setCreating(false)
      }
      toast.success('Nota excluida.')
    },
    onError: () => toast.error('Erro ao excluir nota.'),
  })

  const normalizedSearch = deferredSearch.trim().toLowerCase()
  const filtered = notes
    .filter(note => {
      if (!normalizedSearch) return true
      return (
        note.title.toLowerCase().includes(normalizedSearch)
        || note.content.toLowerCase().includes(normalizedSearch)
      )
    })
    .sort((a, b) => {
      if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
      return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    })

  const activeNote = notes.find(note => note.id === activeId) ?? null
  const editorChoice = activeNote ?? filtered[0] ?? notes[0] ?? null
  const deletingId = deleteMutation.isPending ? deleteMutation.variables : null
  const savePending = createMutation.isPending || updateMutation.isPending
  const pinnedCount = notes.filter(note => note.pinned).length

  function openCreate() {
    setCreating(true)
    setActiveId(null)
  }

  function handleSave(title: string, content: string, pinned: boolean) {
    if (creating) {
      createMutation.mutate({ title, content, pinned })
      return
    }
    if (!activeNote) return
    updateMutation.mutate({ id: activeNote.id, title, content, pinned })
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-[color:var(--ui-bg)] text-[color:var(--ui-text)]">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b app-divider bg-[color:var(--ui-bg)]/90 px-4 py-4 backdrop-blur md:px-8 md:py-5">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-[color:var(--ui-text-meta)]">Workspace Editorial</p>
          <h1 className="mt-1 font-headline text-2xl font-extrabold tracking-tight text-[color:var(--ui-text)]">Notas</h1>
        </div>

        <Button
          onClick={openCreate}
          className="h-10 gap-2 rounded-xl border-0 bg-[color:var(--ui-accent)] px-4 text-[color:var(--ui-bg)]"
        >
          <Plus className="h-4 w-4" />
          Nova nota
        </Button>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-hidden px-4 pb-4 pt-4 md:px-8 md:pb-6">
        <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[1.05fr_1fr]">
          <section className="app-surface flex min-h-0 flex-col overflow-hidden">
            <div className="px-4 pb-3 pt-4 md:px-5 md:pt-5">
              <label htmlFor="notes-search" className="mb-2 block text-xs font-semibold uppercase tracking-[0.16em] text-[color:var(--ui-text-meta)]">
                Buscar
              </label>
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[color:var(--ui-text-meta)]" />
                <input
                  id="notes-search"
                  value={search}
                  onChange={event => setSearch(event.target.value)}
                  placeholder="Buscar por titulo, tags ou conteudo..."
                  className="h-11 w-full rounded-xl bg-[color:var(--ui-bg-alt)] pl-10 pr-3 text-sm text-[color:var(--ui-text)] outline-none ring-1 ring-transparent transition-all placeholder:text-[color:var(--ui-text-meta)] focus:ring-[color:var(--ui-accent)]/60"
                />
              </div>
            </div>

            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 pb-4 md:px-5">
              {isLoading && (
                <div className="space-y-3">
                  {[1, 2, 3].map(index => (
                    <div key={index} className="h-28 animate-pulse rounded-2xl bg-[color:var(--ui-surface-3)]" />
                  ))}
                </div>
              )}

              {!isLoading && filtered.length === 0 && (
                <div className="app-surface-muted flex min-h-[220px] flex-col items-center justify-center px-6 text-center">
                  <StickyNote className="mb-3 h-10 w-10 text-[color:var(--ui-text-meta)]" />
                  <p className="text-sm font-semibold text-[color:var(--ui-text)]">
                    {normalizedSearch ? 'Nenhuma nota encontrada.' : 'Voce ainda nao tem notas.'}
                  </p>
                  <p className="mt-1 text-xs text-[color:var(--ui-text-meta)]">Comece registrando ideias, briefs e observacoes.</p>
                  {!normalizedSearch && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={openCreate}
                      className="mt-4 border-[color:var(--ui-border)] bg-[color:var(--ui-surface-2)] text-[color:var(--ui-text)] hover:border-[color:var(--ui-accent)]/70 hover:bg-[color:var(--ui-surface-3)]"
                    >
                      Criar primeira nota
                    </Button>
                  )}
                </div>
              )}

              {filtered.map(note => (
                <NoteListCard
                  key={note.id}
                  note={note}
                  active={activeId === note.id && !creating}
                  onSelect={() => {
                    setActiveId(note.id)
                    setCreating(false)
                  }}
                  onDelete={() => deleteMutation.mutate(note.id)}
                  deleting={deletingId === note.id}
                />
              ))}
            </div>

            <div className="flex items-center justify-between border-t app-divider bg-[color:var(--ui-surface-1)] px-4 py-3 md:px-5">
              <span className="text-xs text-[color:var(--ui-text-meta)]">{notes.length} notas</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-[color:var(--ui-surface-2)] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-[color:var(--ui-text-dim)]">
                <Pin className="h-3 w-3" />
                {pinnedCount} fixadas
              </span>
            </div>
          </section>

          {(creating || activeNote) ? (
            <NoteEditorPanel
              key={creating ? 'new' : activeNote?.id}
              note={creating ? null : activeNote}
              creating={creating}
              onSave={handleSave}
              onClose={() => {
                setCreating(false)
                setActiveId(null)
              }}
              saving={savePending}
            />
          ) : (
            <section className="app-surface-muted flex min-h-0 flex-col items-center justify-center px-6 text-center">
              <BookText className="mb-3 h-12 w-12 text-[color:var(--ui-text-meta)]" />
              <p className="font-headline text-xl font-bold text-[color:var(--ui-text)]">Selecione uma nota</p>
              <p className="mt-1 max-w-sm text-sm text-[color:var(--ui-text-meta)]">
                Abra uma nota da lista para editar em markdown ou crie uma nova nota no botao superior.
              </p>
              <Button
                onClick={openCreate}
                className="mt-5 h-10 gap-2 rounded-xl border-0 bg-[color:var(--ui-accent)] text-[color:var(--ui-bg)]"
              >
                <Plus className="h-4 w-4" />
                Nova nota
              </Button>
            </section>
          )}
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <article className="app-surface-muted overflow-hidden p-6 md:col-span-2">
            <div>
              <span className="text-[10px] font-black uppercase tracking-[0.22em] text-[color:var(--ui-accent)]">Editor Choice</span>
              <h2 className="mt-2 font-headline text-2xl font-extrabold tracking-tight text-[color:var(--ui-text)]">
                {editorChoice?.title ?? 'Estruture seu repositorio de conhecimento'}
              </h2>
              <p className="mt-2 max-w-2xl text-sm text-[color:var(--ui-text-dim)]">
                {editorChoice?.content
                  ? editorChoice.content.replace(/\s+/g, ' ').slice(0, 220)
                  : 'Padronize notas por tema, com objetivo, contexto e decisoes. Isso reduz retrabalho e acelera refinamentos no pipeline.'}
                {editorChoice?.content && editorChoice.content.length > 220 ? '...' : ''}
              </p>
            </div>
          </article>

          <aside className="app-surface flex flex-col justify-between p-6">
            <div className="mb-6 h-1.5 w-14 rounded-full bg-[color:var(--ui-accent)]" />
            <div>
              <p className="font-headline text-4xl font-black leading-none text-[color:var(--ui-text)]">{notes.length}</p>
              <p className="mt-1 text-xs font-bold uppercase tracking-[0.16em] text-[color:var(--ui-text-meta)]">Notas ativas</p>
            </div>
            <div className="mt-8 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-[color:var(--ui-warning)] shadow-[0_0_10px_rgba(212,168,108,0.7)] animate-pulse" />
              <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-[color:var(--ui-warning)]">Sistema sincronizado</span>
            </div>
            {editorChoice && (
              <p className="mt-4 text-[11px] text-[color:var(--ui-text-meta)]">
                Atualizada em {formatPreciseTimestamp(editorChoice.updated_at)}
              </p>
            )}
          </aside>
        </div>
      </div>

      <div className="pointer-events-none fixed bottom-6 right-6 z-40 hidden items-center gap-3 rounded-full border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)]/85 px-4 py-2 shadow-[0_12px_28px_rgba(0,0,0,0.35)] backdrop-blur md:flex">
        <span className="h-2 w-2 rounded-full bg-[color:var(--ui-warning)] shadow-[0_0_8px_rgba(212,168,108,0.7)]" />
        <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[color:var(--ui-text)]">
          <Sparkles className="h-3 w-3 text-[color:var(--ui-accent)]" />
          System Sync 100%
        </span>
      </div>

      <div className="pointer-events-none fixed bottom-6 left-6 z-40 hidden items-center gap-2 rounded-full border border-[color:var(--ui-border-soft)] bg-[color:var(--ui-surface-2)]/80 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[color:var(--ui-text-dim)] md:flex">
        <Clock3 className="h-3 w-3 text-[color:var(--ui-accent)]" />
        /api/notes conectado
      </div>
    </div>
  )
}
