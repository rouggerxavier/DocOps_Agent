import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  AlertTriangle, BookOpen, CalendarDays, CheckSquare, GraduationCap,
  Plus, Trash2, X, ChevronDown, ChevronUp, Brain,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { apiClient, type DocItem, type StudyPlanItem, type StudyPlanDocResponse } from '@/api/client'

// ── Create Study Plan Dialog ──────────────────────────────────────────────────

function CreateStudyPlanDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [selectedDoc, setSelectedDoc] = useState('')
  const [hoursPerDay, setHoursPerDay] = useState(2)
  const [deadline, setDeadline] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() + 14)
    return d.toISOString().slice(0, 10)
  })
  const [genFlashcards, setGenFlashcards] = useState(true)
  const [numCards, setNumCards] = useState(15)
  const [preferredTime, setPreferredTime] = useState('20:00')
  const [result, setResult] = useState<StudyPlanDocResponse | null>(null)
  const [expandPlan, setExpandPlan] = useState(false)

  const { data: docs } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
  })

  const createMut = useMutation({
    mutationFn: () =>
      apiClient.createStudyPlanFromDoc(selectedDoc, hoursPerDay, deadline, genFlashcards, numCards, preferredTime),
    onSuccess: data => {
      setResult(data)
      onCreated()
      toast.success('Plano de estudos criado!')
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao criar plano'),
  })

  const today = new Date().toISOString().slice(0, 10)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-2xl rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between border-b border-zinc-800 px-6 py-4 shrink-0">
          <div className="flex items-center gap-2">
            <GraduationCap className="h-5 w-5 text-emerald-400" />
            <h2 className="font-semibold text-zinc-100">Novo Plano de Estudos</h2>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}><X className="h-4 w-4" /></Button>
        </div>

        <div className="p-6 space-y-5 overflow-y-auto flex-1">
          {!result && !createMut.isPending && (
            <>
              {/* Documento */}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-zinc-300">Documento</label>
                <select
                  value={selectedDoc}
                  onChange={e => setSelectedDoc(e.target.value)}
                  className="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100"
                >
                  <option value="">Selecione um documento</option>
                  {(docs ?? []).map(d => (
                    <option key={d.file_name} value={d.file_name}>{d.file_name}</option>
                  ))}
                </select>
              </div>

              {/* Horas por dia */}
              <div>
                <label className="mb-1 block text-sm font-medium text-zinc-300">
                  Horas de estudo por dia: <span className="text-emerald-400 font-bold">{hoursPerDay}h</span>
                </label>
                <input
                  type="range" min={1} max={8} step={0.5}
                  value={hoursPerDay}
                  onChange={e => setHoursPerDay(Number(e.target.value))}
                  className="w-full accent-emerald-500"
                />
                <div className="flex justify-between text-[10px] text-zinc-600 mt-0.5">
                  <span>1h</span><span>8h</span>
                </div>
              </div>

              {/* Prazo */}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-zinc-300">Prazo final</label>
                <input
                  type="date"
                  value={deadline}
                  min={today}
                  onChange={e => setDeadline(e.target.value)}
                  className="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100"
                />
              </div>

              {/* Horário preferido */}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-zinc-300">Horário preferido de estudo</label>
                <input
                  type="time"
                  value={preferredTime}
                  onChange={e => setPreferredTime(e.target.value)}
                  className="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100"
                />
                <p className="mt-1 text-xs text-zinc-500">Hora de início das sessões no calendário</p>
              </div>

              {/* Flashcards */}
              <div className="space-y-3">
                <label className="flex items-center gap-3 rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-3 cursor-pointer hover:border-zinc-600 transition-colors">
                  <input
                    type="checkbox"
                    checked={genFlashcards}
                    onChange={e => setGenFlashcards(e.target.checked)}
                    className="h-4 w-4 accent-blue-500"
                  />
                  <div>
                    <p className="text-sm font-medium text-zinc-200">Gerar Flashcards</p>
                    <p className="text-xs text-zinc-500">Cria um deck para revisão espaçada após o prazo</p>
                  </div>
                </label>
                {genFlashcards && (
                  <div className="ml-7 flex items-center gap-3">
                    <span className="text-xs text-zinc-400 shrink-0">Quantidade:</span>
                    <input
                      type="range" min={5} max={30} step={5}
                      value={numCards}
                      onChange={e => setNumCards(Number(e.target.value))}
                      className="flex-1 accent-blue-500"
                    />
                    <span className="text-xs font-medium text-blue-400 w-8 text-right">{numCards}</span>
                  </div>
                )}
              </div>

              <Button
                onClick={() => createMut.mutate()}
                disabled={!selectedDoc || !deadline}
                className="w-full bg-emerald-600 hover:bg-emerald-700 text-white"
              >
                <GraduationCap className="mr-2 h-4 w-4" />
                Criar Plano de Estudos
              </Button>
            </>
          )}

          {createMut.isPending && (
            <div className="flex flex-col items-center justify-center gap-3 py-10">
              <Brain className="h-8 w-8 animate-pulse text-emerald-400" />
              <span className="text-sm text-zinc-400">Gerando plano personalizado com IA...</span>
              <span className="text-xs text-zinc-600">Criando tarefas, sessões e flashcards</span>
            </div>
          )}

          {result && (
            <div className="space-y-4">
              {/* Stats grid */}
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-lg border border-emerald-800 bg-emerald-950/30 p-3 text-center">
                  <p className="text-xs text-emerald-400 mb-1">Tarefas</p>
                  <p className="text-xl font-bold text-emerald-300">{result.tasks_created}</p>
                </div>
                <div className="rounded-lg border border-blue-800 bg-blue-950/30 p-3 text-center">
                  <p className="text-xs text-blue-400 mb-1">Sessões</p>
                  <p className="text-xl font-bold text-blue-300">{result.sessions_count}</p>
                </div>
                <div className="rounded-lg border border-purple-800 bg-purple-950/30 p-3 text-center">
                  <p className="text-xs text-purple-400 mb-1">Flashcards</p>
                  <p className="text-xl font-bold text-purple-300">{result.deck_id ? numCards : '—'}</p>
                </div>
              </div>

              {/* Links */}
              <div className="flex flex-wrap gap-2">
                <a href="/tasks" className="text-xs text-emerald-400 hover:underline">Ver Tarefas →</a>
                <a href="/schedule" className="text-xs text-blue-400 hover:underline">Ver Calendário →</a>
                {result.deck_id && <a href="/flashcards" className="text-xs text-purple-400 hover:underline">Ver Flashcards →</a>}
              </div>

              {/* Conflicts */}
              {result.conflicts && result.conflicts.length > 0 && (
                <div className="rounded-lg border border-amber-800 bg-amber-950/20 p-3 space-y-1">
                  <p className="text-xs font-semibold text-amber-400 flex items-center gap-1">
                    <AlertTriangle className="h-3 w-3" />
                    {result.conflicts.length} conflito(s) de horário detectado(s)
                  </p>
                  {result.conflicts.map((c, i) => (
                    <p key={i} className="text-xs text-zinc-400">
                      <span className="text-zinc-300">{c.date}</span> sessão {c.session_time} conflita com <strong className="text-amber-300">{c.conflicting_with}</strong> ({c.conflicting_time})
                    </p>
                  ))}
                  <a href="/schedule" className="text-xs text-amber-400 hover:underline">Ajustar no Calendário →</a>
                </div>
              )}

              {/* Plan preview */}
              <div>
                <button
                  onClick={() => setExpandPlan(p => !p)}
                  className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200 mb-2"
                >
                  {expandPlan ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                  {expandPlan ? 'Ocultar plano' : 'Ver plano completo'}
                </button>
                {expandPlan && (
                  <div className="prose prose-invert prose-xs max-w-none max-h-80 overflow-y-auto rounded-lg bg-zinc-800 p-4">
                    <ReactMarkdown>{result.plan_text}</ReactMarkdown>
                  </div>
                )}
              </div>

              <Button variant="outline" size="sm" onClick={onClose} className="w-full">Fechar</Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Plan Card ─────────────────────────────────────────────────────────────────

function PlanCard({ plan, onDelete }: { plan: StudyPlanItem; onDelete: (id: number) => void }) {
  const [expanded, setExpanded] = useState(false)

  const deadline = plan.deadline_date
  const isExpired = deadline < new Date().toISOString().slice(0, 10)

  return (
    <Card className="border-zinc-800 hover:border-zinc-700 transition-colors">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-zinc-100 truncate">{plan.titulo}</p>
            <p className="text-xs text-zinc-500 mt-0.5">
              <BookOpen className="inline h-3 w-3 mr-1" />{plan.doc_name}
              {' · '}Prazo: <span className={isExpired ? 'text-red-400' : 'text-zinc-400'}>{deadline}</span>
              {' · '}{plan.hours_per_day}h/dia
            </p>
          </div>
          <Button
            variant="ghost" size="sm"
            onClick={() => onDelete(plan.id)}
            className="text-zinc-600 hover:text-red-400 shrink-0"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>

        {/* Stats row */}
        <div className="flex flex-wrap gap-3 text-xs">
          <span className="flex items-center gap-1 text-emerald-400">
            <CheckSquare className="h-3 w-3" />{plan.tasks_created} tarefas
          </span>
          <span className="flex items-center gap-1 text-blue-400">
            <CalendarDays className="h-3 w-3" />{plan.sessions_count} sessões
          </span>
          {plan.deck_id && (
            <span className="flex items-center gap-1 text-purple-400">
              <Brain className="h-3 w-3" />Flashcards
            </span>
          )}
        </div>

        {/* Expand plan */}
        <button
          onClick={() => setExpanded(p => !p)}
          className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300"
        >
          {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          {expanded ? 'Ocultar plano' : 'Ver plano'}
        </button>

        {expanded && (
          <div className="prose prose-invert prose-xs max-w-none max-h-80 overflow-y-auto rounded-lg bg-zinc-800/60 p-3 border border-zinc-700">
            <ReactMarkdown>{plan.plan_text}</ReactMarkdown>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function StudyPlan() {
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)

  const { data: plans, isLoading, error } = useQuery<StudyPlanItem[]>({
    queryKey: ['study-plans'],
    queryFn: apiClient.listStudyPlans,
    retry: 1,
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => apiClient.deleteStudyPlan(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['study-plans'] })
      toast.success('Plano removido.')
    },
    onError: () => toast.error('Erro ao remover plano.'),
  })

  function handleDelete(id: number) {
    if (confirm('Remover este plano de estudos?')) deleteMut.mutate(id)
  }

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100">Plano de Estudos</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Planos com sessões diárias, tarefas por tópico e flashcards para revisão espaçada
          </p>
        </div>
        <Button
          onClick={() => setShowCreate(true)}
          className="bg-emerald-600 hover:bg-emerald-700 text-white"
        >
          <Plus className="mr-2 h-4 w-4" />
          Novo Plano
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/30 px-4 py-3 text-sm text-red-400">
          Erro ao carregar planos.
        </div>
      )}

      {isLoading && (
        <div className="space-y-3">
          {[1, 2].map(i => <Skeleton key={i} className="h-24 w-full" />)}
        </div>
      )}

      {!isLoading && (!plans || plans.length === 0) && !error && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12">
            <GraduationCap className="h-12 w-12 text-zinc-600" />
            <p className="font-medium text-zinc-300">Nenhum plano criado ainda</p>
            <p className="text-sm text-zinc-500 text-center max-w-sm">
              Crie um plano para um documento e obtenha sessões de estudo no calendário,
              tarefas por tópico e flashcards automaticamente.
            </p>
            <Button onClick={() => setShowCreate(true)} className="bg-emerald-600 hover:bg-emerald-700 text-white">
              <Plus className="mr-2 h-4 w-4" />Criar Plano
            </Button>
          </CardContent>
        </Card>
      )}

      {plans && plans.length > 0 && (
        <div className="space-y-3">
          {plans.map(plan => (
            <PlanCard key={plan.id} plan={plan} onDelete={handleDelete} />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateStudyPlanDialog
          onClose={() => setShowCreate(false)}
          onCreated={() => qc.invalidateQueries({ queryKey: ['study-plans'] })}
        />
      )}
    </div>
  )
}
