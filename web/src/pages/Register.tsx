import { useState, type FormEvent } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Loader2 } from 'lucide-react'
import { useGoogleLogin } from '@react-oauth/google'
import { useAuth } from '@/auth/AuthProvider'

const GOOGLE_CONFIGURED = !!import.meta.env.VITE_GOOGLE_CLIENT_ID

function GoogleButton({ disabled }: { disabled: boolean }) {
  const { loginWithGoogle } = useAuth()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)

  const handleGoogle = useGoogleLogin({
    onSuccess: async tokenResponse => {
      setLoading(true)
      try {
        await loginWithGoogle(tokenResponse.access_token)
        navigate('/dashboard', { replace: true })
      } catch {
        toast.error('Erro ao autenticar com Google.')
      } finally {
        setLoading(false)
      }
    },
    onError: () => toast.error('Login com Google cancelado ou falhou.'),
  })

  return (
    <button
      type="button"
      onClick={() => handleGoogle()}
      disabled={loading || disabled}
      className="w-full flex items-center justify-center gap-3 py-3 px-4 rounded-lg text-[#e5e2e1] transition-colors active:scale-95 duration-200 disabled:opacity-60 disabled:cursor-not-allowed"
      style={{ backgroundColor: '#2a2a2a' }}
      onMouseEnter={e => { if (!loading && !disabled) (e.currentTarget).style.backgroundColor = '#3a3939' }}
      onMouseLeave={e => { (e.currentTarget).style.backgroundColor = '#2a2a2a' }}
    >
      {loading
        ? <Loader2 className="h-[18px] w-[18px] animate-spin shrink-0" />
        : (
          <svg className="h-[18px] w-[18px] shrink-0" viewBox="0 0 24 24" aria-hidden="true">
            <path fill="currentColor" d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z" />
          </svg>
        )
      }
      <span className="text-sm font-medium">Continuar com Google</span>
    </button>
  )
}

export function Register() {
  const { register, login } = useAuth()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const preferredName = name.trim()
    if (!preferredName || !email || !password) {
      toast.error('Preencha todos os campos.')
      return
    }
    if (password.length < 8) {
      toast.error('Senha deve ter pelo menos 8 caracteres.')
      return
    }
    setLoading(true)
    try {
      await register(preferredName, email, password)
      await login(email, password)
      toast.success('Conta criada com sucesso!')
      navigate('/dashboard', { replace: true })
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Erro ao criar conta.'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  const inputBase: React.CSSProperties = {
    backgroundColor: '#1c1b1b',
    border: '1px solid transparent',
    fontFamily: "'Inter', sans-serif",
  }
  const inputFocus: React.CSSProperties = {
    backgroundColor: '#2a2a2a',
    border: '1px solid rgba(208, 228, 255, 0.3)',
  }

  function handleFocus(e: React.FocusEvent<HTMLInputElement>) {
    Object.assign(e.currentTarget.style, inputFocus)
  }
  function handleBlur(e: React.FocusEvent<HTMLInputElement>) {
    Object.assign(e.currentTarget.style, inputBase)
  }

  const inputClass =
    'w-full rounded-lg py-3.5 sm:py-4 px-4 text-[#e5e2e1] outline-none transition-all disabled:opacity-50'

  return (
    <div
      className="min-h-screen text-[#e5e2e1] selection:bg-[#d0e4ff]/30 selection:text-[#d0e4ff]"
      style={{ backgroundColor: '#131313', fontFamily: "'Inter', sans-serif" }}
    >
      {/* Background — cinematic light leaks */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute -top-[10%] -left-[10%] w-[50%] h-[50%] rounded-full blur-[120px]"
          style={{ backgroundColor: 'rgba(208, 228, 255, 0.05)' }} />
        <div className="absolute top-[20%] -right-[5%] w-[40%] h-[40%] rounded-full blur-[100px]"
          style={{ backgroundColor: 'rgba(254, 183, 133, 0.05)' }} />
        <div className="absolute -bottom-[10%] left-[20%] w-[60%] h-[40%] rounded-full blur-[120px]"
          style={{ backgroundColor: 'rgba(163, 201, 248, 0.05)' }} />
      </div>

      {/* Main content */}
      <main className="relative z-10 min-h-screen flex flex-col items-center justify-center px-4 py-12 sm:p-8">

        {/* Brand header */}
        <header className="mb-10 sm:mb-12 text-center">
          <div className="inline-flex items-center gap-2 mb-6 sm:mb-8">
            <span
              className="text-xl sm:text-2xl font-extrabold tracking-tighter text-[#d0e4ff]"
              style={{ fontFamily: "'Manrope', sans-serif" }}
            >
              DocOps Agent
            </span>
          </div>
          <h1
            className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-[#e5e2e1] tracking-tight mb-3"
            style={{ fontFamily: "'Manrope', sans-serif" }}
          >
            Comece agora.
          </h1>
          <p className="text-[#c2c7cf] text-base sm:text-lg max-w-sm sm:max-w-md mx-auto">
            Crie sua conta e transforme documentos em conhecimento.
          </p>
        </header>

        {/* Glass card */}
        <div
          className="w-full max-w-sm sm:max-w-md rounded-xl p-6 sm:p-8 lg:p-10"
          style={{
            background: 'rgba(53, 53, 52, 0.6)',
            backdropFilter: 'blur(24px)',
            WebkitBackdropFilter: 'blur(24px)',
            border: '1px solid rgba(208, 228, 255, 0.1)',
            boxShadow: '0 20px 50px rgba(0, 0, 0, 0.5), 0 0 15px rgba(208, 228, 255, 0.03)',
          }}
        >
          <form onSubmit={handleSubmit} className="space-y-5 sm:space-y-6">
            {/* Como quer ser chamado */}
            <div className="space-y-2">
              <label
                htmlFor="name"
                className="block text-[11px] font-semibold uppercase tracking-widest text-[#c2c7cf]"
                style={{ fontFamily: "'Inter', sans-serif" }}
              >
                Como você quer ser chamado?
              </label>
              <input
                id="name"
                type="text"
                name="name"
                placeholder="Ex.: Rougger"
                value={name}
                onChange={e => setName(e.target.value)}
                disabled={loading}
                autoComplete="nickname"
                required
                className={inputClass}
                style={inputBase}
                onFocus={handleFocus}
                onBlur={handleBlur}
              />
              <p className="text-[11px] text-[#c2c7cf]/60">
                Esse nome vai aparecer no seu painel.
              </p>
            </div>

            {/* Email */}
            <div className="space-y-2">
              <label
                htmlFor="email"
                className="block text-[11px] font-semibold uppercase tracking-widest text-[#c2c7cf]"
                style={{ fontFamily: "'Inter', sans-serif" }}
              >
                E-mail
              </label>
              <input
                id="email"
                type="email"
                name="email"
                placeholder="nome@exemplo.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                disabled={loading}
                autoComplete="email"
                required
                className={inputClass}
                style={inputBase}
                onFocus={handleFocus}
                onBlur={handleBlur}
              />
            </div>

            {/* Senha */}
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <label
                  htmlFor="password"
                  className="block text-[11px] font-semibold uppercase tracking-widest text-[#c2c7cf]"
                  style={{ fontFamily: "'Inter', sans-serif" }}
                >
                  Senha
                </label>
                <span className="text-[10px] text-[#c2c7cf]/50" style={{ fontFamily: "'Inter', sans-serif" }}>
                  mín. 8 caracteres
                </span>
              </div>
              <input
                id="password"
                type="password"
                name="password"
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                disabled={loading}
                autoComplete="new-password"
                required
                minLength={8}
                className={inputClass}
                style={inputBase}
                onFocus={handleFocus}
                onBlur={handleBlur}
              />
              {/* Password strength hint */}
              {password.length > 0 && (
                <div className="flex gap-1 mt-1.5">
                  {[...Array(4)].map((_, i) => (
                    <div
                      key={i}
                      className="h-0.5 flex-1 rounded-full transition-all duration-300"
                      style={{
                        backgroundColor: password.length >= (i + 1) * 3
                          ? password.length >= 12
                            ? '#6da97b'
                            : password.length >= 8
                              ? '#d0e4ff'
                              : '#feb785'
                          : '#42474e',
                      }}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full font-semibold py-3.5 sm:py-4 rounded-xl transition-all disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2 active:scale-[0.98]"
              style={{
                backgroundColor: '#d0e4ff',
                color: '#003258',
                boxShadow: '0 4px 24px rgba(208, 228, 255, 0.1)',
                fontFamily: "'Inter', sans-serif",
              }}
              onMouseEnter={e => {
                if (!loading) (e.currentTarget as HTMLButtonElement).style.filter = 'brightness(1.1)'
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLButtonElement).style.filter = ''
              }}
            >
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              Criar conta
            </button>
          </form>

          {/* Divider */}
          <div className="relative my-7 sm:my-8">
            <div className="absolute inset-0 flex items-center" aria-hidden="true">
              <div className="w-full" style={{ borderTop: '1px solid rgba(66, 71, 78, 0.3)' }} />
            </div>
            <div className="relative flex justify-center">
              <span
                className="px-4 text-[10px] uppercase tracking-widest text-[#c2c7cf]"
                style={{ backgroundColor: 'rgba(42, 42, 42, 0.9)', fontFamily: "'Inter', sans-serif" }}
              >
                Ou continue com
              </span>
            </div>
          </div>

          {/* Google OAuth — só renderiza o hook quando o Client ID está configurado */}
          {GOOGLE_CONFIGURED ? (
            <GoogleButton disabled={loading} />
          ) : (
            <button
              type="button"
              disabled
              title="Configure VITE_GOOGLE_CLIENT_ID para ativar"
              className="w-full flex items-center justify-center gap-3 py-3 px-4 rounded-lg text-[#e5e2e1] opacity-40 cursor-not-allowed"
              style={{ backgroundColor: '#2a2a2a' }}
            >
              <svg className="h-[18px] w-[18px] shrink-0" viewBox="0 0 24 24" aria-hidden="true">
                <path fill="currentColor" d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z" />
              </svg>
              <span className="text-sm font-medium">Continuar com Google</span>
            </button>
          )}

          {/* Footer link */}
          <p className="mt-8 sm:mt-10 text-center text-sm text-[#c2c7cf]">
            Já tem conta?{' '}
            <Link
              to="/login"
              className="font-semibold ml-1 transition-colors hover:underline underline-offset-4"
              style={{ color: '#feb785' }}
            >
              Entrar
            </Link>
          </p>
        </div>

        {/* Gradient accent line */}
        <div className="mt-14 sm:mt-16 max-w-4xl w-full hidden md:block opacity-30">
          <div className="h-px bg-gradient-to-r from-transparent via-[#d0e4ff]/40 to-transparent" />
        </div>

        {/* Voltar */}
        <p className="mt-6 text-center text-xs text-[#c2c7cf]/40">
          <Link to="/" className="hover:text-[#c2c7cf]/70 transition-colors">← Voltar ao início</Link>
        </p>
      </main>

      {/* Footer */}
      <footer className="w-full py-10 sm:py-12 relative z-10" style={{ backgroundColor: '#131313' }}>
        <div className="flex flex-col items-center gap-5 max-w-7xl mx-auto px-6 sm:px-8">
          <div
            className="font-bold text-[#e5e2e1]"
            style={{ fontFamily: "'Manrope', sans-serif" }}
          >
            DocOps Agent
          </div>
          <div className="flex flex-wrap justify-center gap-6 sm:gap-8">
            {['Privacidade', 'Termos', 'Documentação', 'Suporte'].map(item => (
              <a
                key={item}
                href="#"
                className="text-xs text-[#c2c7cf]/50 transition-colors"
                style={{ fontFamily: "'Inter', sans-serif" }}
                onMouseEnter={e => (e.currentTarget.style.color = 'rgba(254, 183, 133, 0.7)')}
                onMouseLeave={e => (e.currentTarget.style.color = 'rgba(194, 199, 207, 0.5)')}
              >
                {item}
              </a>
            ))}
          </div>
          <p
            className="text-xs text-[#c2c7cf]/40"
            style={{ fontFamily: "'Inter', sans-serif" }}
          >
            © 2025 DocOps Agent. The Cognitive Luminary.
          </p>
        </div>
      </footer>
    </div>
  )
}
