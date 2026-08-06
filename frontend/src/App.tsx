import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { AuthProvider } from '@/lib/auth'
import { ChatPage } from '@/pages/chat/ChatPage'
import { LoginPage } from '@/pages/login/LoginPage'
import { NotFoundPage } from '@/pages/not-found/NotFoundPage'

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<Navigate to="/chat" replace />} />
            <Route path="/chat" element={<ChatPage />} />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
