import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { ConfigProvider } from './lib/config'
import { ConsolePage } from './pages/ConsolePage'

export default function App() {
  return (
    <ConfigProvider>
      <BrowserRouter>
        <Shell>
          <Routes>
            <Route path="/" element={<ConsolePage />} />
            <Route path="/run/:runId" element={<ConsolePage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Shell>
      </BrowserRouter>
    </ConfigProvider>
  )
}
