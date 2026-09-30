import { Navigate, useParams } from 'react-router-dom'

/** Old `/chat` links predate the picker and always meant the document copilot. */
export function LegacyChatRedirect() {
  const { threadId } = useParams<{ threadId: string }>()
  return <Navigate to={threadId ? `/documents/${threadId}` : '/documents'} replace />
}
