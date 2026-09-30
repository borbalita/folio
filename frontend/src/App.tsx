import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { AgentRoute } from '@/components/auth/AgentRoute'
import { MeGate } from '@/components/auth/MeGate'
import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { AuthProvider } from '@/lib/auth'
import { ChatEmptyState } from '@/pages/chat/ChatEmptyState'
import { ChatPage } from '@/pages/chat/ChatPage'
import { ChatThreadPage } from '@/pages/chat/ChatThreadPage'
import { LegacyChatRedirect } from '@/pages/chat/LegacyChatRedirect'
import { LoginPage } from '@/pages/login/LoginPage'
import { NotFoundPage } from '@/pages/not-found/NotFoundPage'
import { AgentPickerPage } from '@/pages/picker/AgentPickerPage'

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<MeGate />}>
              <Route path="/" element={<AgentPickerPage />} />
              <Route
                path="/documents"
                element={<ChatPage key="documents" agentName="documents" />}
              >
                <Route index element={<ChatEmptyState />} />
                <Route path=":threadId" element={<ChatThreadPage />} />
              </Route>
              <Route element={<AgentRoute agent="email" />}>
                <Route path="/email" element={<ChatPage key="email" agentName="email" />}>
                  <Route index element={<ChatEmptyState />} />
                  <Route path=":threadId" element={<ChatThreadPage />} />
                </Route>
              </Route>
              <Route path="/chat" element={<LegacyChatRedirect />} />
              <Route path="/chat/:threadId" element={<LegacyChatRedirect />} />
            </Route>
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
