import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, ApiError, type ServerConfig } from './api'

interface ConfigState {
  config: ServerConfig | null
  error: string | null
  reload: () => void
}

const ConfigContext = createContext<ConfigState>({ config: null, error: null, reload: () => undefined })

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<ServerConfig | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    api
      .config()
      .then((value) => {
        if (cancelled) return
        setConfig(value)
        setError(null)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : String(err))
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  const reload = useCallback(() => {
    setAttempt((n) => n + 1)
  }, [])

  return <ConfigContext value={{ config, error, reload }}>{children}</ConfigContext>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useServerConfig(): ConfigState {
  return useContext(ConfigContext)
}
