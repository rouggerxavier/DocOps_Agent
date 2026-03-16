import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// ── Types ─────────────────────────────────────────────────────────────────────

export interface DocItem {
  doc_id: string
  file_name: string
  source: string
  chunk_count: number
}

export interface SourceItem {
  fonte_n: number
  file_name: string
  page: string
  snippet: string
  chunk_id: string
}

export interface ChatResponse {
  answer: string
  sources: SourceItem[]
  intent: string
  session_id: string | null
}

export interface IngestResponse {
  files_loaded: number
  chunks_indexed: number
  file_names: string[]
}

export interface ArtifactItem {
  filename: string
  size: number
  created_at: string
  artifact_type: string
  title: string | null
}

export interface ArtifactResponse {
  answer: string
  filename: string
  path: string
}

export interface SummarizeResponse {
  answer: string
  artifact_path: string | null
  artifact_filename?: string | null
}

export interface CompareResponse {
  answer: string
  artifact_path: string | null
}

// ── API functions ─────────────────────────────────────────────────────────────

export const apiClient = {
  health: () => api.get('/api/health').then(r => r.data),

  listDocs: (): Promise<DocItem[]> =>
    api.get('/api/docs').then(r => r.data),

  chat: (
    message: string,
    session_id?: string,
    top_k?: number,
    doc_names?: string[]
  ): Promise<ChatResponse> =>
    api.post('/api/chat', { message, session_id, top_k, doc_names }).then(r => r.data),

  ingestPath: (path: string, chunk_size = 0, chunk_overlap = 0): Promise<IngestResponse> =>
    api.post('/api/ingest', { path, chunk_size, chunk_overlap }).then(r => r.data),

  ingestUpload: (files: File[], chunk_size = 0, chunk_overlap = 0): Promise<IngestResponse> => {
    const form = new FormData()
    files.forEach(f => form.append('files', f))
    form.append('chunk_size', String(chunk_size))
    form.append('chunk_overlap', String(chunk_overlap))
    return api.post('/api/ingest/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },

  summarize: (doc: string, save = true, summary_mode: 'brief' | 'deep' = 'brief'): Promise<SummarizeResponse> =>
    api.post('/api/summarize', { doc, save, summary_mode }).then(r => r.data),

  compare: (doc1: string, doc2: string, save = false): Promise<CompareResponse> =>
    api.post('/api/compare', { doc1, doc2, save }).then(r => r.data),

  createArtifact: (
    type: string,
    topic: string,
    output?: string,
    doc_names?: string[]
  ): Promise<ArtifactResponse> =>
    api.post('/api/artifact', { type, topic, output, doc_names }).then(r => r.data),

  listArtifacts: (): Promise<ArtifactItem[]> =>
    api.get('/api/artifacts').then(r => r.data),

  getArtifactText: (filename: string): Promise<string> =>
    api
      .get(`/api/artifacts/${encodeURIComponent(filename)}`, { responseType: 'text' })
      .then(r => (typeof r.data === 'string' ? r.data : String(r.data))),

  getArtifactBlob: (filename: string): Promise<Blob> =>
    api
      .get(`/api/artifacts/${encodeURIComponent(filename)}`, { responseType: 'blob' })
      .then(r => r.data as Blob),

  getArtifactPdfBlob: (filename: string): Promise<Blob> =>
    api
      .get(`/api/artifacts/${encodeURIComponent(filename)}/pdf`, { responseType: 'blob' })
      .then(r => r.data as Blob),

  downloadArtifactUrl: (filename: string): string =>
    `${BASE_URL}/api/artifacts/${encodeURIComponent(filename)}`,

  downloadArtifactPdfUrl: (filename: string): string =>
    `${BASE_URL}/api/artifacts/${encodeURIComponent(filename)}/pdf`,
}
