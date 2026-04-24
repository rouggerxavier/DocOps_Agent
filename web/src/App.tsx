import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { useEffect } from 'react'
import { AuthProvider, useAuth } from '@/auth/AuthProvider'
import { AppErrorBoundary } from '@/components/errors/AppErrorBoundary'
import { Layout } from '@/components/layout/Layout'
import { CapabilitiesProvider } from '@/features/CapabilitiesProvider'
import { OnboardingProvider } from '@/onboarding/OnboardingContext'
import { Artifacts } from '@/pages/Artifacts'
import { Chat } from '@/pages/Chat'
import { Dashboard } from '@/pages/Dashboard'
import { Docs } from '@/pages/Docs'
import { Flashcards } from '@/pages/Flashcards'
import { Ingest } from '@/pages/Ingest'
import { Landing } from '@/pages/Landing'
import { Login } from '@/pages/Login'
import { Notes } from '@/pages/Notes'
import { ReadingKanban } from '@/pages/ReadingKanban'
import { Register } from '@/pages/Register'
import { Schedule } from '@/pages/Schedule'
import { Preferences } from '@/pages/Preferences'
import { StudyPlan } from '@/pages/StudyPlan'
import { Tasks } from '@/pages/Tasks'
import { MobileMenu } from '@/pages/MobileMenu'

const PAGE_TITLES: Record<string, string> = {
  '/': 'DocOps Agent',
  '/dashboard': 'Dashboard',
  '/ingest': 'Inserção',
  '/chat': 'Chat',
  '/docs': 'Documentos',
  '/artifacts': 'Artefatos',
  '/schedule': 'Calendário',
  '/notes': 'Notas',
  '/tasks': 'Tarefas',
  '/flashcards': 'Flashcards',
  '/studyplan': 'Plano de Estudos',
  '/more': 'Menu',
  '/settings': 'Configurações',
  '/kanban': 'Kanban de Leitura',
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
  if (token) return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <TitleUpdater />
          <AppErrorBoundary>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/login" element={<RedirectIfAuth><Login /></RedirectIfAuth>} />
              <Route path="/register" element={<RedirectIfAuth><Register /></RedirectIfAuth>} />
              <Route element={<RequireAuth><CapabilitiesProvider><OnboardingProvider><Layout /></OnboardingProvider></CapabilitiesProvider></RequireAuth>}>
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/ingest" element={<Ingest />} />
                <Route path="/chat" element={<Chat />} />
                <Route path="/docs" element={<Docs />} />
                <Route path="/artifacts" element={<Artifacts />} />
                <Route path="/schedule" element={<Schedule />} />
                <Route path="/notes" element={<Notes />} />
                <Route path="/tasks" element={<Tasks />} />
                <Route path="/flashcards" element={<Flashcards />} />
                <Route path="/studyplan" element={<StudyPlan />} />
                <Route path="/more" element={<MobileMenu />} />
                <Route path="/settings" element={<Preferences />} />
                <Route path="/kanban" element={<ReadingKanban />} />
              </Route>
            </Routes>
          </AppErrorBoundary>
          <Toaster
            theme="dark"
            position="top-right"
            toastOptions={{
              style: {
                background: '#121821',
                border: '1px solid #27303A',
                color: '#F3F1EB',
              },
            }}
          />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
