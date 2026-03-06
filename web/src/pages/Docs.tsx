import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { FileText, BookOpen, GitCompare, Loader2, Search } from 'lucide-react'
import { toast } from 'sonner'
import ReactMarkdown from 'react-markdown'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { apiClient, type DocItem } from '@/api/client'

function SummarizeDialog({
  doc,
  onClose,
}: {
  doc: string
  onClose: () => void
}) {
  const [result, setResult] = useState('')
  const [mode, setMode] = useState<'brief' | 'deep'>('brief')

  const mutation = useMutation({
    mutationFn: () => apiClient.summarize(doc, false, mode),
    onSuccess: data => setResult(data.answer),
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao resumir'),
  })

  const modeLabel = mode === 'brief' ? 'Resumo Breve' : 'Resumo Aprofundado'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-2xl rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-800 px-6 py-4">
          <h2 className="font-semibold text-zinc-100">Resumo: {doc}</h2>
          <Button variant="ghost" size="sm" onClick={onClose}>✕</Button>
        </div>
        <div className="p-6 space-y-4">
          {!result && !mutation.isPending && (
            <>
              {/* Mode selector */}
              <div>
                <p className="mb-2 text-sm font-medium text-zinc-300">Tipo de resumo:</p>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => setMode('brief')}
                    className={`rounded-lg border px-4 py-3 text-left transition-colors ${
                      mode === 'brief'
                        ? 'border-blue-500 bg-blue-500/10 text-blue-300'
                        : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600'
                    }`}
                  >
                    <p className="text-sm font-semibold">Resumo Breve</p>
                    <p className="mt-0.5 text-xs opacity-70">
                      Síntese concisa — até 300 palavras com os pontos essenciais
                    </p>
                  </button>
                  <button
                    onClick={() => setMode('deep')}
                    className={`rounded-lg border px-4 py-3 text-left transition-colors ${
                      mode === 'deep'
                        ? 'border-violet-500 bg-violet-500/10 text-violet-300'
                        : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600'
                    }`}
                  >
                    <p className="text-sm font-semibold">Resumo Aprofundado</p>
                    <p className="mt-0.5 text-xs opacity-70">
                      Análise completa seção por seção com detalhes técnicos
                    </p>
                  </button>
                </div>
              </div>
              <Button onClick={() => mutation.mutate()} className="w-full">
                <BookOpen className="mr-2 h-4 w-4" />
                Gerar {modeLabel}
              </Button>
            </>
          )}
          {mutation.isPending && (
            <div className="flex flex-col items-center justify-center gap-3 py-8">
              <Loader2 className="h-6 w-6 animate-spin text-blue-400" />
              <span className="text-sm text-zinc-400">
                {mode === 'deep'
                  ? 'Analisando documento em profundidade...'
                  : 'Gerando resumo breve...'}
              </span>
            </div>
          )}
          {result && (
            <>
              <div className="flex items-center justify-between">
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                  mode === 'brief'
                    ? 'bg-blue-500/15 text-blue-300'
                    : 'bg-violet-500/15 text-violet-300'
                }`}>
                  {modeLabel}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs text-zinc-500 hover:text-zinc-300"
                  onClick={() => { setResult(''); mutation.reset() }}
                >
                  Gerar outro
                </Button>
              </div>
              <div className="prose prose-invert prose-sm max-w-none max-h-[32rem] overflow-y-auto">
                <ReactMarkdown>{result}</ReactMarkdown>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function CompareDialog({
  doc1,
  allDocs,
  onClose,
}: {
  doc1: string
  allDocs: DocItem[]
  onClose: () => void
}) {
  const [doc2, setDoc2] = useState('')
  const [result, setResult] = useState('')

  const mutation = useMutation({
    mutationFn: () => apiClient.compare(doc1, doc2, false),
    onSuccess: data => setResult(data.answer),
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erro ao comparar'),
  })

  const others = allDocs.filter(d => d.file_name !== doc1)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-2xl rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-800 px-6 py-4">
          <h2 className="font-semibold text-zinc-100">Comparar: {doc1}</h2>
          <Button variant="ghost" size="sm" onClick={onClose}>✕</Button>
        </div>
        <div className="p-6 space-y-4">
          {!result && (
            <>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-zinc-300">
                  Comparar com:
                </label>
                <select
                  value={doc2}
                  onChange={e => setDoc2(e.target.value)}
                  className="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100"
                >
                  <option value="">Selecione um documento</option>
                  {others.map(d => (
                    <option key={d.file_name} value={d.file_name}>
                      {d.file_name}
                    </option>
                  ))}
                </select>
              </div>
              <Button
                onClick={() => mutation.mutate()}
                disabled={!doc2 || mutation.isPending}
                className="w-full"
              >
                {mutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Comparando...
                  </>
                ) : (
                  <>
                    <GitCompare className="mr-2 h-4 w-4" />
                    Comparar
                  </>
                )}
              </Button>
            </>
          )}
          {result && (
            <div className="prose prose-invert prose-sm max-w-none max-h-96 overflow-y-auto">
              <ReactMarkdown>{result}</ReactMarkdown>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function Docs() {
  const [search, setSearch] = useState('')
  const [summarizeDoc, setSummarizeDoc] = useState<string | null>(null)
  const [compareDoc, setCompareDoc] = useState<string | null>(null)

  const { data: docs, isLoading, error } = useQuery<DocItem[]>({
    queryKey: ['docs'],
    queryFn: apiClient.listDocs,
    retry: 1,
  })

  const filtered = docs?.filter(d =>
    d.file_name.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-zinc-100">Documentos Indexados</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Gerencie e opere sobre seus documentos
        </p>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
        <Input
          placeholder="Buscar documento..."
          className="pl-10"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/30 px-4 py-3 text-sm text-red-400">
          Erro ao carregar documentos. Certifique-se que o servidor está rodando.
        </div>
      )}

      {isLoading && (
        <div className="space-y-3">
          {[1, 2, 3, 4].map(i => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      )}

      {!isLoading && (!filtered || filtered.length === 0) && !error && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12">
            <FileText className="h-12 w-12 text-zinc-600" />
            <p className="font-medium text-zinc-300">
              {search ? 'Nenhum documento encontrado' : 'Nenhum documento indexado'}
            </p>
            <p className="text-sm text-zinc-500">
              {search
                ? 'Tente outro termo de busca'
                : 'Use a página de Ingestão para adicionar documentos'}
            </p>
          </CardContent>
        </Card>
      )}

      {filtered && filtered.length > 0 && (
        <div className="space-y-2">
          {filtered.map(doc => (
            <Card key={doc.file_name} className="hover:border-zinc-700 transition-colors">
              <CardContent className="flex items-center justify-between py-4">
                <div className="flex items-center gap-3 min-w-0">
                  <FileText className="h-5 w-5 shrink-0 text-blue-400" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-zinc-100 truncate">
                      {doc.file_name}
                    </p>
                    <p className="text-xs text-zinc-500 truncate">{doc.source}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0 ml-4">
                  <Badge variant="secondary">{doc.chunk_count} chunks</Badge>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSummarizeDoc(doc.file_name)}
                  >
                    <BookOpen className="h-4 w-4" />
                    Resumir
                  </Button>
                  {docs && docs.length > 1 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setCompareDoc(doc.file_name)}
                    >
                      <GitCompare className="h-4 w-4" />
                      Comparar
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Dialogs */}
      {summarizeDoc && (
        <SummarizeDialog doc={summarizeDoc} onClose={() => setSummarizeDoc(null)} />
      )}
      {compareDoc && docs && (
        <CompareDialog
          doc1={compareDoc}
          allDocs={docs}
          onClose={() => setCompareDoc(null)}
        />
      )}
    </div>
  )
}
