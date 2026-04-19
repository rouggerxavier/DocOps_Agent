import { useNavigate } from 'react-router-dom'
import {
  BookOpen,
  ChevronRight,
  FileText,
  Layers,
  Settings,
  StickyNote,
  Upload,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/auth/AuthProvider'
import { apiClient, type ArtifactItem } from '@/api/client'
import { MKicker } from '@/components/mobile/Primitives'

const MENU_ITEMS = [
  { path: '/docs',      icon: FileText,  label: 'Documentos',       sub: 'Todos os seus arquivos indexados' },
  { path: '/notes',     icon: StickyNote, label: 'Notas',           sub: 'Anotações pessoais vinculadas a docs' },
  { path: '/artifacts', icon: Layers,    label: 'Artefatos',        sub: 'Resumos, mapas, quizzes, planos' },
  { path: '/kanban',    icon: BookOpen,  label: 'Kanban de Leitura', sub: 'Organize sua fila de leitura' },
  { path: '/ingest',    icon: Upload,    label: 'Inserir documento', sub: 'Upload, clip, caminho, foto' },
  { path: '/settings',  icon: Settings,  label: 'Preferências',     sub: 'Conta, IA, aparência' },
]

const ARTIFACT_ICONS: Record<string, string> = {
  Resumo: '📄', Checklist: '✓', Plano: '⋯', Mapa: '◈', Quiz: '?', Redação: '✎',
}

export function MobileMore() {
  const navigate = useNavigate()
  const { user } = useAuth()

  const { data: artifacts } = useQuery<ArtifactItem[]>({
    queryKey: ['artifacts', { sort_by: 'created_at', sort_order: 'desc' }],
    queryFn: () => apiClient.listArtifacts({ sort_by: 'created_at', sort_order: 'desc' }),
    retry: 1,
  })

  const recentArtifacts = artifacts?.slice(0, 3) ?? []

  const s1 = 'var(--ui-surface-1)'
  const borderSoft = 'var(--ui-border-soft)'
  const accent = 'var(--ui-accent)'
  const text = 'var(--ui-text)'
  const textDim = 'var(--ui-text-dim)'
  const textMeta = 'var(--ui-text-meta)'
  const s2 = 'var(--ui-surface-2)'
  const s3 = 'var(--ui-surface-3)'
  const radius = 16

  return (
    <div
      style={{
        padding: '8px 18px 120px',
        fontFamily: "'Manrope', 'Segoe UI', system-ui, sans-serif",
      }}
    >
      {/* ── User card ────────────────────────────────────────────────────── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: 14,
          background: s1,
          border: `1px solid ${borderSoft}`,
          borderRadius: radius,
          marginBottom: 16,
        }}
      >
        <div
          style={{
            width: 46,
            height: 46,
            borderRadius: 999,
            background: accent,
            color: 'var(--ui-bg)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 18,
            fontWeight: 800,
            flexShrink: 0,
          }}
        >
          {user?.email?.[0]?.toUpperCase() ?? 'U'}
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: 14,
              fontWeight: 700,
              color: text,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {user?.email?.split('@')[0] ?? 'Usuário'}
          </div>
          <div style={{ fontSize: 11, color: textMeta, marginTop: 1 }}>
            {user?.email ?? ''}
          </div>
        </div>

        <button
          onClick={() => navigate('/settings')}
          aria-label="Preferências"
          style={{
            width: 34,
            height: 34,
            borderRadius: 999,
            background: s3,
            color: textDim,
            border: 'none',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
          }}
        >
          <Settings size={15} />
        </button>
      </div>

      {/* ── Recent artifacts ─────────────────────────────────────────────── */}
      {recentArtifacts.length > 0 && (
        <>
          <MKicker style={{ marginBottom: 10 }}>Artefatos recentes</MKicker>
          <div
            style={{
              background: s1,
              border: `1px solid ${borderSoft}`,
              borderRadius: radius,
              overflow: 'hidden',
              marginBottom: 18,
            }}
          >
            {recentArtifacts.map((a, i) => {
              const iconEmoji = ARTIFACT_ICONS[a.artifact_type ?? ''] ?? '📄'
              return (
                <button
                  key={a.id}
                  onClick={() => navigate('/artifacts')}
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: '12px 14px',
                    borderTop: i === 0 ? 'none' : `1px solid ${borderSoft}`,
                    background: 'transparent',
                    border: 'none',
                    borderTopWidth: i === 0 ? 0 : 1,
                    borderTopStyle: 'solid',
                    borderTopColor: borderSoft,
                    textAlign: 'left',
                    color: 'inherit',
                    cursor: 'pointer',
                  }}
                >
                  <div
                    style={{
                      width: 34,
                      height: 34,
                      borderRadius: 8,
                      background: s2,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 16,
                      flexShrink: 0,
                    }}
                  >
                    {iconEmoji}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: text,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {a.filename.replace(/\.[^.]+$/, '')}
                    </div>
                    <div
                      style={{
                        fontSize: 10,
                        color: textMeta,
                        marginTop: 2,
                        fontFamily: "'IBM Plex Mono', monospace",
                      }}
                    >
                      {a.artifact_type ?? 'Artefato'}
                    </div>
                  </div>
                  <ChevronRight size={14} color={textMeta} />
                </button>
              )
            })}
          </div>
        </>
      )}

      {/* ── Navigation links ─────────────────────────────────────────────── */}
      <div
        style={{
          background: s1,
          border: `1px solid ${borderSoft}`,
          borderRadius: radius,
          overflow: 'hidden',
        }}
      >
        {MENU_ITEMS.map(({ path, icon: Icon, label, sub }, i) => (
          <button
            key={path}
            onClick={() => navigate(path)}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '13px 14px',
              borderTop: i === 0 ? 'none' : `1px solid ${borderSoft}`,
              background: 'transparent',
              border: 'none',
              borderTopWidth: i === 0 ? 0 : 1,
              borderTopStyle: 'solid',
              borderTopColor: borderSoft,
              textAlign: 'left',
              cursor: 'pointer',
              color: 'inherit',
            }}
          >
            <Icon size={16} color={textDim} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: text }}>
                {label}
              </div>
              <div style={{ fontSize: 11, color: textMeta, marginTop: 1 }}>
                {sub}
              </div>
            </div>
            <ChevronRight size={14} color={textMeta} />
          </button>
        ))}
      </div>

      <div
        style={{
          marginTop: 18,
          fontSize: 10,
          color: textMeta,
          textAlign: 'center',
          fontFamily: "'IBM Plex Mono', monospace",
        }}
      >
        DocOps Agent · mobile
      </div>
    </div>
  )
}
