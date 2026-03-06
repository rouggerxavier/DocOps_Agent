import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { AuthProvider, useAuth } from '@/auth/AuthProvider'
import { Layout } from '@/components/layout/Layout'
import { Dashboard } from '@/pages/Dashboard'
import { Ingest } from '@/pages/Ingest'
import { Chat } from '@/pages/Chat'
import { Docs } from '@/pages/Docs'
import { Artifacts } from '@/pages/Artifacts'
import { Login } from '@/pages/Login'
import { Register } from '@/pages/Register'

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
          <Routes>
            <Route path="/login" element={<RedirectIfAuth><Login /></RedirectIfAuth>} />
            <Route path="/register" element={<RedirectIfAuth><Register /></RedirectIfAuth>} />
            <Route element={<RequireAuth><Layout /></RequireAuth>}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/ingest" element={<Ingest />} />
              <Route path="/chat" element={<Chat />} />
              <Route path="/docs" element={<Docs />} />
              <Route path="/artifacts" element={<Artifacts />} />
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
