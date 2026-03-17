import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { useEffect } from 'react'
import { AuthProvider, useAuth } from '@/auth/AuthProvider'
import { Layout } from '@/components/layout/Layout'
import { Dashboard } from '@/pages/Dashboard'
import { Ingest } from '@/pages/Ingest'
import { Chat } from '@/pages/Chat'
import { Docs } from '@/pages/Docs'
import { Artifacts } from '@/pages/Artifacts'
import { Schedule } from '@/pages/Schedule'
import { Notes } from '@/pages/Notes'
import { Tasks } from '@/pages/Tasks'
import { Flashcards } from '@/pages/Flashcards'
import { StudyPlan } from '@/pages/StudyPlan'
import { Login } from '@/pages/Login'
import { Register } from '@/pages/Register'

const PAGE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/ingest': 'Inserção',
  '/chat': 'Chat',
  '/docs': 'Documentos',
  '/artifacts': 'Artefatos',
  '/schedule': 'Calendário',
  '/notes': 'Notas',
  '/tasks': 'Tarefas',
  '/flashcards': 'Flashcards',
  '/studyplan': 'Plano de Estudos',
  '/login': 'Login',
  '/register': 'Criar conta',
}

function TitleUpdater() {
  const location = useLocation()
  useEffect(() => {
    const label = PAGE_TITLES[location.pathname] ?? 'DocOps Agent'
    document.title = `${label} — DocOps Agent`
  }, [location.pathname])
  return null
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
})

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { token, loading } = useAuth()
  if (loading) return null
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

function RedirectIfAuth({ children }: { children: React.ReactNode }) {
  const { token, loading } = useAuth()
  if (loading) return null
  if (token) return <Navigate to="/" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <TitleUpdater />
          <Routes>
            <Route path="/login" element={<RedirectIfAuth><Login /></RedirectIfAuth>} />
            <Route path="/register" element={<RedirectIfAuth><Register /></RedirectIfAuth>} />
            <Route element={<RequireAuth><Layout /></RequireAuth>}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/ingest" element={<Ingest />} />
              <Route path="/chat" element={<Chat />} />
              <Route path="/docs" element={<Docs />} />
              <Route path="/artifacts" element={<Artifacts />} />
              <Route path="/schedule" element={<Schedule />} />
              <Route path="/notes" element={<Notes />} />
              <Route path="/tasks" element={<Tasks />} />
              <Route path="/flashcards" element={<Flashcards />} />
              <Route path="/studyplan" element={<StudyPlan />} />
            </Route>
          </Routes>
          <Toaster
            theme="dark"
            position="top-right"
            toastOptions={{
              style: { background: '#18181b', border: '1px solid #27272a', color: '#f4f4f5' },
            }}
          />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
