import { createContext, useContext, useEffect, useState } from 'react'

export type AppTheme = 'dark' | 'light'

interface ThemeContextValue {
  theme: AppTheme
  setTheme: (t: AppTheme) => void
  toggleTheme: () => void
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: 'dark',
  setTheme: () => {},
  toggleTheme: () => {},
})

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<AppTheme>(() => {
    const saved = localStorage.getItem('docops:theme')
    return saved === 'light' ? 'light' : 'dark'
  })

  useEffect(() => {
    localStorage.setItem('docops:theme', theme)
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  const setTheme = (t: AppTheme) => setThemeState(t)
  const toggleTheme = () => setThemeState(t => (t === 'dark' ? 'light' : 'dark'))

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useAppTheme() {
  return useContext(ThemeContext)
}
