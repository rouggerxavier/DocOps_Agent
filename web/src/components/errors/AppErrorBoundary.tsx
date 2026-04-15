import type { ReactNode } from 'react'
import { Component } from 'react'

type AppErrorBoundaryProps = {
  children: ReactNode
}

type AppErrorBoundaryState = {
  hasError: boolean
}

export class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  constructor(props: AppErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(): AppErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: unknown) {
    // Keep diagnostics in console while avoiding a full blank screen for the user.
    console.error('[AppErrorBoundary] runtime error captured', error)
  }

  private handleReload = () => {
    window.location.reload()
  }

  private handleGoDashboard = () => {
    window.location.href = '/dashboard'
  }

  override render() {
    if (!this.state.hasError) {
      return this.props.children
    }

    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100">
        <div className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center px-6 text-center">
          <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Falha de renderizacao</p>
          <h1 className="mt-3 text-2xl font-semibold text-zinc-100">A tela encontrou um erro inesperado.</h1>
          <p className="mt-3 text-sm text-zinc-400">
            Ja registramos o problema no console. Tente recarregar a pagina ou voltar ao dashboard.
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
            <button
              type="button"
              onClick={this.handleReload}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm text-zinc-100 transition-colors hover:bg-zinc-800"
            >
              Recarregar pagina
            </button>
            <button
              type="button"
              onClick={this.handleGoDashboard}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm text-zinc-100 transition-colors hover:bg-zinc-800"
            >
              Ir para dashboard
            </button>
          </div>
        </div>
      </div>
    )
  }
}

