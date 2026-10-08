import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

/** "console" is MAGI's own look; "classic" echoes the show's MAGI display. */
export type Theme = 'console' | 'classic'

const STORAGE_KEY = 'magi.theme'

function storedTheme(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'classic' ? 'classic' : 'console'
  } catch {
    return 'console' // storage blocked (private window, previews)
  }
}

interface ThemeState {
  theme: Theme
  setTheme: (theme: Theme) => void
}

const ThemeContext = createContext<ThemeState>({ theme: 'console', setTheme: () => undefined })

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(storedTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // not persisted; the choice still applies for this visit
    }
  }, [])

  return <ThemeContext value={{ theme, setTheme }}>{children}</ThemeContext>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTheme(): ThemeState {
  return useContext(ThemeContext)
}

const KANJI = {
  APPROVE: '承認',
  APPROVED: '承認',
  DENY: '否定',
  DENIED: '否定',
  ABSTAIN: '保留',
  DEADLOCK: '保留',
} as const

/** The Japanese word the classic display shows for a vote or outcome. */
// eslint-disable-next-line react-refresh/only-export-components
export function kanjiFor(value: keyof typeof KANJI): string {
  return KANJI[value]
}
