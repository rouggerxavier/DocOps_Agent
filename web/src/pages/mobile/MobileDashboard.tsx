import { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Clock,
  FileText,
  Layers,
  RefreshCw,
} from 'lucide-react'
import {
  apiClient,
  type ArtifactItem,
  type BriefingResponse,
  type CalendarOverview,
  type DailyQuestionResponse,
  type DocItem,
  type EvaluateAnswerResponse,
} from '@/api/client'
import { useAuth } from '@/auth/AuthProvider'

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
  danger:     'var(--ui-danger)',
  radius:     16,
  mono:       "'IBM Plex Mono', monospace",
  sans:       "'Manrope', 'Segoe UI', system-ui, sans-serif",
}

// ── Section header ─────────────────────────────────────────────────────────────
function SectionLabel({ children }: { children: string }) {
  return (
    <div style={{
      fontSize: 10, fontFamily: T.mono, letterSpacing: '0.16em',
      textTransform: 'uppercase', color: T.meta, marginBottom: 8,
    }}>
      {children}
    </div>
  )
}

// ── Card wrapper ───────────────────────────────────────────────────────────────
function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: T.s1,
      border: `1px solid ${T.border}`,
      borderRadius: T.radius,
      overflow: 'hidden',
      ...style,
    }}>
      {children}
    </div>
  )
}

// ── Metric chip (inline stat) ─────────────────────────────────────────────────
function MetricChip({
  icon: Icon,
  label,
  value,
  loading,
}: {
  icon: typeof FileText
  label: string
  value: number
  loading?: boolean
}) {
  return (
    <div style={{
      flex: 1,
      background: T.s1,
      border: `1px solid ${T.border}`,
      borderRadius: T.radius,
      padding: '14px 14px 12px',
    }}>
      <div style={{
        width: 32, height: 32, borderRadius: 8,
        background: T.accentSoft,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        marginBottom: 10,
      }}>
        <Icon size={15} color={T.accent} />
      </div>
      <div style={{ fontSize: 10, fontFamily: T.mono, letterSpacing: '0.12em', textTransform: 'uppercase', color: T.meta, marginBottom: 4 }}>
        {label}
      </div>
      {loading ? (
        <div style={{ height: 24, width: 40, background: T.s3, borderRadius: 6 }} />
      ) : (
        <div style={{ fontSize: 26, fontWeight: 800, color: T.text, letterSpacing: '-0.03em', lineHeight: 1 }}>
          {value}
        </div>
      )}
    </div>
  )
}

// ── Daily question (compact) ──────────────────────────────────────────────────
function DailyQuestion({ data, loading }: { data: DailyQuestionResponse | undefined; loading: boolean }) {
  const [open, setOpen] = useState(false)
  const [answer, setAnswer] = useState('')
  const [evaluation, setEvaluation] = useState<EvaluateAnswerResponse | null>(null)
  const [showHint, setShowHint] = useState(false)

  const evaluate = useMutation({
    mutationFn: () => apiClient.evaluateAnswer(data!.question!, answer, data?.answer_hint ?? ''),
    onSuccess: (r) => setEvaluation(r),
  })

  if (loading) {
    return (
      <div style={{ height: 80, background: T.s1, border: `1px solid ${T.border}`, borderRadius: T.radius }} />
    )
  }
  if (!data?.question) return null

  const scoreTone: Record<string, { bg: string; color: string; label: string }> = {
    excelente: { bg: 'rgba(52,211,153,0.12)', color: '#34d399', label: 'Excelente' },
    bom:       { bg: T.accentSoft, color: T.accent, label: 'Bom' },
    parcial:   { bg: 'rgba(251,191,36,0.12)', color: '#fbbf24', label: 'Parcial' },
    incorreto: { bg: 'rgba(248,113,113,0.12)', color: '#f87171', label: 'Incorreto' },
    sem_resposta: { bg: T.s2, color: T.dim, label: 'Sem resposta' },
  }
  const tone = evaluation ? (scoreTone[evaluation.score] ?? scoreTone.parcial) : null

  return (
    <Card>
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 12,
          padding: '14px 14px', background: 'transparent', border: 'none',
          textAlign: 'left', cursor: 'pointer', color: 'inherit',
        }}
      >
        <span style={{ fontSize: 9, fontFamily: T.mono, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#fbbf24' }}>
          Pergunta do dia
        </span>
        <span style={{ flex: 1, fontSize: 13, fontWeight: 600, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: open ? 'normal' : 'nowrap' }}>
          {data.question}
        </span>
        <ChevronDown size={14} color={T.meta} style={{ flexShrink: 0, transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }} />
      </button>

      {open && (
        <div style={{ padding: '0 14px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {!evaluation ? (
            <>
              <textarea
                value={answer}
                onChange={e => setAnswer(e.target.value)}
                placeholder="Articule sua resposta..."
                rows={3}
                style={{
                  width: '100%', background: T.s2, border: `1px solid ${T.border}`,
                  borderRadius: 10, padding: '10px 12px', fontSize: 13,
                  color: T.text, fontFamily: T.sans, resize: 'none', outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
              <button
                onClick={() => evaluate.mutate()}
                disabled={answer.trim().length < 3 || evaluate.isPending}
                style={{
                  width: '100%', height: 40, borderRadius: 10,
                  background: answer.trim().length >= 3 ? T.accent : T.s3,
                  color: answer.trim().length >= 3 ? T.bg : T.dim,
                  border: 'none', fontSize: 13, fontWeight: 700,
                  cursor: answer.trim().length >= 3 ? 'pointer' : 'not-allowed',
                }}
              >
                {evaluate.isPending ? 'Avaliando...' : 'Avaliar resposta'}
              </button>
              {data.answer_hint && (
                <button
                  onClick={() => setShowHint(v => !v)}
                  style={{ background: 'none', border: 'none', color: T.accent, fontSize: 12, cursor: 'pointer', textAlign: 'left', display: 'flex', alignItems: 'center', gap: 4 }}
                >
                  <ChevronDown size={12} style={{ transform: showHint ? 'rotate(180deg)' : 'none' }} />
                  {showHint ? 'Ocultar dica' : 'Ver dica'}
                </button>
              )}
              {showHint && data.answer_hint && (
                <div style={{ background: T.s2, borderRadius: 8, padding: '8px 10px', fontSize: 12, color: T.dim }}>
                  {data.answer_hint}
                </div>
              )}
            </>
          ) : (
            <div style={{ background: tone!.bg, borderRadius: 10, padding: '10px 12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ fontSize: 10, fontFamily: T.mono, letterSpacing: '0.14em', textTransform: 'uppercase', color: tone!.color }}>
                  {tone!.label}
                </span>
                <button
                  onClick={() => { setEvaluation(null); setAnswer('') }}
                  style={{ background: 'none', border: 'none', fontSize: 11, color: T.meta, cursor: 'pointer' }}
                >
                  Tentar novamente
                </button>
              </div>
              <p style={{ fontSize: 13, color: T.text, lineHeight: 1.5 }}>{evaluation.feedback}</p>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

// ── Schedule item row ─────────────────────────────────────────────────────────
function ScheduleRow({ time, title, note, isLast }: { time: string; title: string; note: string | null; isLast: boolean }) {
  return (
    <div style={{
      display: 'flex', gap: 10, padding: '11px 14px',
      borderBottom: isLast ? 'none' : `1px solid ${T.border}`,
    }}>
      <div style={{ width: 40, flexShrink: 0, fontSize: 11, fontFamily: T.mono, color: T.meta, paddingTop: 1 }}>
        {time}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{title}</div>
        {note && <div style={{ fontSize: 11, color: T.dim, marginTop: 1 }}>{note}</div>}
      </div>
    </div>
  )
}

// ── Doc row ───────────────────────────────────────────────────────────────────
function DocRow({ name, source, isLast }: { name: string; source: string; isLast: boolean }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px',
      borderBottom: isLast ? 'none' : `1px solid ${T.border}`,
    }}>
      <div style={{
        width: 32, height: 32, borderRadius: 8, background: T.accentSoft,
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
      }}>
        <FileText size={13} color={T.accent} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {name}
        </div>
        <div style={{ fontSize: 10, color: T.meta, fontFamily: T.mono }}>{source || 'local'}</div>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export function MobileDashboard() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [now, setNow] = useState(() => new Date())
  const [syncing, setSyncing] = useState(false)

  const { data: docs, isLoading: docsLoading, error: docsError } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
    retry: 1,
  })
  const { data: artifacts, isLoading: artifactsLoading } = useQuery<ArtifactItem[]>({
    queryKey: ['artifacts'],
    queryFn: () => apiClient.listArtifacts(),
    retry: 1,
  })
  const { data: calendar, isLoading: calendarLoading, refetch: refetchCalendar } = useQuery<CalendarOverview>({
    queryKey: ['calendar-overview', 'today'],
    queryFn: () => apiClient.getCalendarOverview(),
    retry: 1,
  })
  const { data: briefing, refetch: refetchBriefing } = useQuery<BriefingResponse>({
    queryKey: ['briefing'],
    queryFn: apiClient.getBriefing,
    staleTime: 60_000,
    retry: 1,
  })
  const hasDocuments = !docsLoading && !!docs && docs.length > 0
  const { data: dailyQuestion, isLoading: questionLoading } = useQuery<DailyQuestionResponse>({
    queryKey: ['daily-question'],
    queryFn: apiClient.getDailyQuestion,
    staleTime: 12 * 60 * 60 * 1000,
    retry: false,
    enabled: hasDocuments,
  })

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 30_000)
    return () => window.clearInterval(id)
  }, [])

  const firstName = user?.name?.trim().split(/\s+/)[0] || 'arquiteto'
  const todayLabel = now.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long' })
  const greeting = briefing?.greeting ?? 'Olá'
  const overdueCount = briefing?.overdue_tasks.length ?? 0
  const apiOnline = !docsError

  const liveNow = calendar?.current_schedule_item
  const nextItem = calendar?.next_schedule_item

  const todaySchedule = (calendar?.today_schedule ?? []).slice(0, 3)
  const todayReminders = (calendar?.today_reminders ?? []).slice(0, 2)
  const recentDocs = (docs ?? []).slice(0, 3)

  async function handleSync() {
    if (syncing) return
    setSyncing(true)
    try { await Promise.all([refetchBriefing(), refetchCalendar()]) }
    finally { setSyncing(false) }
  }

  return (
    <div style={{ padding: '16px 16px 100px', fontFamily: T.sans, display: 'flex', flexDirection: 'column', gap: 18 }}>

      {/* ── Greeting ─────────────────────────────────────────────────────── */}
      <div style={{
        background: T.s1, border: `1px solid ${T.border}`,
        borderRadius: T.radius, padding: 16, position: 'relative', overflow: 'hidden',
      }}>
        {/* subtle glow */}
        <div style={{
          position: 'absolute', top: -40, right: -40, width: 120, height: 120,
          borderRadius: '50%', background: T.accentSoft, filter: 'blur(32px)',
          pointerEvents: 'none',
        }} />

        <div style={{ position: 'relative' }}>
          <div style={{ fontSize: 10, fontFamily: T.mono, letterSpacing: '0.16em', textTransform: 'uppercase', color: T.meta, marginBottom: 6 }}>
            {todayLabel}
          </div>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, color: T.text, letterSpacing: '-0.03em', lineHeight: 1.1 }}>
            {greeting}, {firstName}.
          </h1>

          {/* live context */}
          {(liveNow || nextItem) && !calendarLoading && (
            <div style={{ marginTop: 10, fontSize: 12, color: T.dim, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Clock size={12} color={T.accent} />
              {liveNow
                ? `Agora: ${liveNow.title} até ${liveNow.end_time}`
                : `Próxima: ${nextItem!.title} às ${nextItem!.start_time}`}
            </div>
          )}

          {/* status row */}
          <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 5,
              background: T.s2, border: `1px solid ${T.border}`,
              borderRadius: 999, padding: '4px 10px', fontSize: 11, color: T.dim,
            }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: apiOnline ? '#34d399' : '#f87171' }} />
              {apiOnline ? 'API online' : 'API offline'}
            </span>

            {overdueCount > 0 && (
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                background: 'rgba(251,191,36,0.10)', border: '1px solid rgba(251,191,36,0.25)',
                borderRadius: 999, padding: '4px 10px', fontSize: 11, color: '#fbbf24',
              }}>
                <AlertTriangle size={10} />
                {overdueCount} {overdueCount === 1 ? 'pendência' : 'pendências'}
              </span>
            )}

            <button
              onClick={handleSync}
              disabled={syncing}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                background: 'transparent', border: 'none', padding: '4px 0',
                fontSize: 11, color: T.accent, cursor: 'pointer',
              }}
            >
              <RefreshCw size={11} style={{ animation: syncing ? 'spin 1s linear infinite' : 'none' }} />
              {syncing ? 'Atualizando...' : 'Atualizar'}
            </button>
          </div>
        </div>
      </div>

      {/* ── Stats row ────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 10 }}>
        <MetricChip icon={FileText} label="Documentos" value={docs?.length ?? 0} loading={docsLoading} />
        <MetricChip icon={Layers} label="Artefatos" value={artifacts?.length ?? 0} loading={artifactsLoading} />
      </div>

      {/* ── Daily question ───────────────────────────────────────────────── */}
      {(hasDocuments || questionLoading) && (
        <div>
          <SectionLabel>Pergunta do dia</SectionLabel>
          <DailyQuestion data={dailyQuestion} loading={questionLoading} />
        </div>
      )}

      {/* ── Agenda hoje ──────────────────────────────────────────────────── */}
      {(calendarLoading || todaySchedule.length > 0) && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <SectionLabel>Agenda hoje</SectionLabel>
            <button
              onClick={() => navigate('/studyplan')}
              style={{ background: 'none', border: 'none', fontSize: 11, color: T.accent, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 3 }}
            >
              Ver agenda <ChevronRight size={11} />
            </button>
          </div>
          {calendarLoading ? (
            <div style={{ height: 80, background: T.s1, border: `1px solid ${T.border}`, borderRadius: T.radius }} />
          ) : (
            <Card>
              {todaySchedule.map((item, i) => (
                <ScheduleRow
                  key={item.id}
                  time={item.start_time}
                  title={item.title}
                  note={item.note}
                  isLast={i === todaySchedule.length - 1}
                />
              ))}
            </Card>
          )}
        </div>
      )}

      {/* ── Lembretes ────────────────────────────────────────────────────── */}
      {todayReminders.length > 0 && (
        <div>
          <SectionLabel>Lembretes</SectionLabel>
          <Card>
            {todayReminders.map((r, i) => (
              <div key={r.id} style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: '11px 14px',
                borderBottom: i === todayReminders.length - 1 ? 'none' : `1px solid ${T.border}`,
              }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#fbbf24', flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{r.title}</div>
                  <div style={{ fontSize: 10, color: T.meta, fontFamily: T.mono }}>
                    {r.all_day
                      ? 'Dia inteiro'
                      : new Date(r.starts_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                    {r.note ? ` · ${r.note}` : ''}
                  </div>
                </div>
              </div>
            ))}
          </Card>
        </div>
      )}

      {/* ── Documentos recentes ───────────────────────────────────────────── */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <SectionLabel>Documentos recentes</SectionLabel>
          {hasDocuments && (
            <button
              onClick={() => navigate('/docs')}
              style={{ background: 'none', border: 'none', fontSize: 11, color: T.accent, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 3 }}
            >
              Ver todos <ChevronRight size={11} />
            </button>
          )}
        </div>

        {docsLoading ? (
          <div style={{ height: 80, background: T.s1, border: `1px solid ${T.border}`, borderRadius: T.radius }} />
        ) : !hasDocuments ? (
          <Card style={{ padding: 16 }}>
            <div style={{ fontSize: 13, color: T.dim, marginBottom: 12 }}>
              Nenhum documento ainda. Adicione o primeiro para começar.
            </div>
            <button
              onClick={() => navigate('/ingest')}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                background: T.accent, color: T.bg, border: 'none',
                borderRadius: 10, padding: '8px 14px', fontSize: 13, fontWeight: 700, cursor: 'pointer',
              }}
            >
              <FileText size={13} /> Inserir documento
            </button>
          </Card>
        ) : (
          <Card>
            {recentDocs.map((doc, i) => (
              <DocRow key={doc.doc_id} name={doc.file_name} source={doc.source} isLast={i === recentDocs.length - 1} />
            ))}
          </Card>
        )}
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg) } }
      `}</style>
    </div>
  )
}
