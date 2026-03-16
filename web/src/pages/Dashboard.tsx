import { useQuery } from '@tanstack/react-query'
import { CalendarClock, FileText, Layers, BookOpen, Zap } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { apiClient, type CalendarOverview, type DocItem } from '@/api/client'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'

function StatCard({
  title,
  value,
  icon: Icon,
  description,
  loading,
}: {
  title: string
  value: string | number
  icon: React.ElementType
  description?: string
  loading?: boolean
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-zinc-400">{title}</CardTitle>
        <Icon className="h-4 w-4 text-zinc-500" />
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-8 w-16" />
        ) : (
          <div className="text-2xl font-bold text-zinc-100">{value}</div>
        )}
        {description && <p className="mt-1 text-xs text-zinc-500">{description}</p>}
      </CardContent>
    </Card>
  )
}

export function Dashboard() {
  const { data: docs, isLoading, error } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
    retry: 1,
  })
  const { data: calendarOverview, isLoading: isCalendarLoading } = useQuery<CalendarOverview>({
    queryKey: ['calendar-overview', 'today'],
    queryFn: () => apiClient.getCalendarOverview(),
    retry: 1,
  })

  const totalChunks = docs?.reduce((sum, d) => sum + d.chunk_count, 0) ?? 0

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-zinc-100">Dashboard</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Visão geral do seu agente RAG local
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/30 px-4 py-3 text-sm text-red-400">
          Não foi possível conectar à API. Certifique-se que o servidor está rodando:{' '}
          <code className="font-mono">python -m docops serve</code>
        </div>
      )}

      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Documentos Indexados"
          value={docs?.length ?? 0}
          icon={FileText}
          description="PDFs, Markdown e texto"
          loading={isLoading}
        />
        <StatCard
          title="Total de Chunks"
          value={totalChunks.toLocaleString()}
          icon={Layers}
          description="Fragmentos vetorizados"
          loading={isLoading}
        />
        <StatCard
          title="Status da API"
          value={error ? 'Offline' : 'Online'}
          icon={Zap}
          description="FastAPI + Chroma"
          loading={isLoading}
        />
        <StatCard
          title="Lembretes Hoje"
          value={calendarOverview?.today_reminders.length ?? 0}
          icon={CalendarClock}
          description="Agenda do dia"
          loading={isCalendarLoading}
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-zinc-400">Agora no Cronograma</CardTitle>
          </CardHeader>
          <CardContent>
            {isCalendarLoading ? (
              <Skeleton className="h-8 w-3/4" />
            ) : calendarOverview?.current_schedule_item ? (
              <>
                <p className="text-lg font-semibold text-emerald-300">
                  {calendarOverview.current_schedule_item.title}
                </p>
                <p className="text-xs text-zinc-500">
                  {calendarOverview.current_schedule_item.start_time} às {calendarOverview.current_schedule_item.end_time}
                </p>
              </>
            ) : (
              <p className="text-sm text-zinc-500">Sem atividade fixa neste horário.</p>
            )}
            {!isCalendarLoading && calendarOverview?.next_schedule_item && (
              <p className="mt-2 text-xs text-zinc-400">
                Próximo: {calendarOverview.next_schedule_item.title} às {calendarOverview.next_schedule_item.start_time}
              </p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-zinc-400">Lembretes de Hoje</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {isCalendarLoading && [1, 2].map(i => <Skeleton key={i} className="h-6 w-full" />)}
            {!isCalendarLoading && (!calendarOverview || calendarOverview.today_reminders.length === 0) && (
              <p className="text-sm text-zinc-500">Nenhum lembrete para hoje.</p>
            )}
            {!isCalendarLoading && calendarOverview?.today_reminders.slice(0, 3).map(rem => (
              <div key={rem.id} className="rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2">
                <p className="text-sm text-zinc-200">{rem.title}</p>
                <p className="text-xs text-zinc-500">
                  {rem.all_day
                    ? 'Dia inteiro'
                    : new Date(rem.starts_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                  {rem.note ? ` • ${rem.note}` : ''}
                </p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Document list preview */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-zinc-100">Documentos Recentes</h2>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/docs">Ver todos</Link>
          </Button>
        </div>

        {isLoading && (
          <div className="space-y-2">
            {[1, 2, 3].map(i => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        )}

        {!isLoading && (!docs || docs.length === 0) && (
          <Card>
            <CardContent className="flex flex-col items-center gap-4 py-12">
              <BookOpen className="h-12 w-12 text-zinc-600" />
              <div className="text-center">
                <p className="font-medium text-zinc-300">Nenhum documento indexado</p>
                <p className="mt-1 text-sm text-zinc-500">
                  Adicione documentos para começar a usar o agente
                </p>
              </div>
              <Button asChild>
                <Link to="/ingest">Ingerir Documentos</Link>
              </Button>
            </CardContent>
          </Card>
        )}

        {!isLoading && docs && docs.length > 0 && (
          <div className="space-y-2">
            {docs.slice(0, 5).map(doc => (
              <Card key={doc.file_name} className="hover:border-zinc-700 transition-colors">
                <CardContent className="flex items-center justify-between py-4">
                  <div className="flex items-center gap-3">
                    <FileText className="h-4 w-4 shrink-0 text-blue-400" />
                    <div>
                      <p className="text-sm font-medium text-zinc-100">{doc.file_name}</p>
                      <p className="text-xs text-zinc-500">{doc.source}</p>
                    </div>
                  </div>
                  <span className="shrink-0 rounded-full bg-zinc-800 px-2.5 py-0.5 text-xs text-zinc-400">
                    {doc.chunk_count} chunks
                  </span>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Quick actions */}
      <div>
        <h2 className="mb-4 text-lg font-semibold text-zinc-100">Ações Rápidas</h2>
        <div className="grid gap-4 sm:grid-cols-4">
          <Button variant="outline" className="h-auto flex-col gap-2 py-4" asChild>
            <Link to="/ingest">
              <FileText className="h-5 w-5" />
              <span>Ingerir Documentos</span>
            </Link>
          </Button>
          <Button variant="outline" className="h-auto flex-col gap-2 py-4" asChild>
            <Link to="/chat">
              <BookOpen className="h-5 w-5" />
              <span>Iniciar Chat</span>
            </Link>
          </Button>
          <Button variant="outline" className="h-auto flex-col gap-2 py-4" asChild>
            <Link to="/artifacts">
              <Layers className="h-5 w-5" />
              <span>Ver Artefatos</span>
            </Link>
          </Button>
          <Button variant="outline" className="h-auto flex-col gap-2 py-4" asChild>
            <Link to="/schedule">
              <CalendarClock className="h-5 w-5" />
              <span>Calendário</span>
            </Link>
          </Button>
        </div>
      </div>
    </div>
  )
}
