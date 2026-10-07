import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { ConfigProvider } from './lib/config'
import { ConsolePage } from './pages/ConsolePage'
import { ReplayIndexPage } from './pages/ReplayIndexPage'
import { ReplayPage } from './pages/ReplayPage'

export default function App() {
  return (
    <ConfigProvider>
      <BrowserRouter>
        <Shell>
          <Routes>
            <Route path="/" element={<ConsolePage />} />
            <Route path="/run/:runId" element={<ConsolePage />} />
            <Route path="/replay" element={<ReplayIndexPage />} />
            <Route path="/replay/:traceId" element={<ReplayPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Shell>
      </BrowserRouter>
    </ConfigProvider>
  )
}
