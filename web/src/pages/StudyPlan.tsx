import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { GraduationCap, Loader2, BookOpen, Download } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { apiClient, type DocItem } from '@/api/client'
import { cn } from '@/lib/utils'

export function StudyPlan() {
  const [topic, setTopic] = useState('')
  const [days, setDays] = useState(7)
  const [selectedDocs, setSelectedDocs] = useState<string[]>([])
  const [result, setResult] = useState<{ plan: string; filename: string | null; pdfFilename: string | null } | null>(null)

  const { data: docs = [] } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
  })

  const generateMut = useMutation({
    mutationFn: () => apiClient.createStudyPlan(topic, days, selectedDocs),
    onSuccess: data => {
      setResult({ plan: data.plan, filename: data.artifact_filename, pdfFilename: data.pdf_filename ?? null })
      toast.success('Plano de estudos gerado!')
    },
    onError: () => toast.error('Erro ao gerar plano de estudos.'),
  })

  function toggleDoc(name: string) {
    setSelectedDocs(prev =>
      prev.includes(name) ? prev.filter(d => d !== name) : [...prev, name],
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-zinc-100">Plano de Estudos</h1>
        <p className="mt-0.5 text-sm text-zinc-500">
          Gere um plano estruturado dia a dia usando IA
        </p>
      </div>

      {!result ? (
        <div className="mx-auto max-w-xl space-y-6">
          {/* Topic */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-300">O que você quer estudar?</label>
            <Input
              value={topic}
              onChange={e => setTopic(e.target.value)}
              placeholder="Ex: Cálculo Integral, React Hooks, História do Brasil..."
              className="bg-zinc-900 border-zinc-800"
            />
          </div>

          {/* Days slider */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-300">
              Prazo: <span className="text-blue-400">{days} dias</span>
            </label>
            <input
              type="range"
              min={1}
              max={90}
              value={days}
              onChange={e => setDays(Number(e.target.value))}
              className="w-full"
            />
            <div className="flex justify-between text-[10px] text-zinc-700">
              <span>1 dia</span>
              <span>90 dias</span>
            </div>
          </div>

          {/* Doc selection */}
          {docs.length > 0 && (
            <div className="space-y-2">
              <label className="text-sm font-medium text-zinc-300">
                Basear em documentos <span className="text-zinc-600">(opcional)</span>
              </label>
              <div className="max-h-40 overflow-y-auto space-y-1 rounded-xl border border-zinc-800 bg-zinc-900 p-3">
                {docs.map(doc => (
                  <button
                    key={doc.file_name}
                    onClick={() => toggleDoc(doc.file_name)}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs transition-colors text-left',
                      selectedDocs.includes(doc.file_name)
                        ? 'bg-blue-600/20 text-blue-400'
                        : 'text-zinc-400 hover:bg-zinc-800',
                    )}
                  >
                    <BookOpen className="h-3 w-3 shrink-0" />
                    <span className="truncate">{doc.file_name}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Generate */}
          <Button
            className="w-full gap-2"
            onClick={() => generateMut.mutate()}
            disabled={!topic.trim() || generateMut.isPending}
          >
            {generateMut.isPending
              ? <Loader2 className="h-4 w-4 animate-spin" />
              : <GraduationCap className="h-4 w-4" />
            }
            Gerar Plano de Estudos
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <Button variant="ghost" size="sm" onClick={() => setResult(null)}>
              Gerar outro
            </Button>
            <div className="flex items-center gap-3">
              {result.filename && (
                <a
                  href={apiClient.downloadArtifactUrl(result.filename)}
                  target="_blank"
                  rel="noopener"
                  className="flex items-center gap-1 text-xs text-blue-400 hover:underline"
                >
                  <Download className="h-3 w-3" /> Baixar .md
                </a>
              )}
              {result.pdfFilename && (
                <a
                  href={apiClient.downloadArtifactUrl(result.pdfFilename)}
                  target="_blank"
                  rel="noopener"
                  className="flex items-center gap-1 text-xs text-emerald-400 hover:underline"
                >
                  <Download className="h-3 w-3" /> Baixar .pdf
                </a>
              )}
            </div>
          </div>

          <Card className="border-zinc-800 bg-zinc-900">
            <CardContent className="p-6">
              <div className="prose prose-invert prose-sm max-w-none
                  prose-headings:text-zinc-100 prose-h1:text-lg prose-h2:text-base prose-h3:text-sm
                  prose-p:text-zinc-400 prose-li:text-zinc-400
                  prose-strong:text-zinc-200 prose-em:text-zinc-300
                  prose-code:text-blue-300 prose-code:bg-zinc-800 prose-code:px-1 prose-code:rounded
                  prose-hr:border-zinc-800">
                <ReactMarkdown>{result.plan}</ReactMarkdown>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
