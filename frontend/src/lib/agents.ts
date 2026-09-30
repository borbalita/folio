import type { AgentName } from '@/lib/api'

export interface AgentInfo {
  name: AgentName
  title: string
  description: string
  path: string
  emptyTitle: string
  emptyHint: string
  placeholder: string
}

export const AGENTS: Record<AgentName, AgentInfo> = {
  documents: {
    name: 'documents',
    title: 'Document Copilot',
    description: 'Ask questions about 10-K filings, with citations to the filing text.',
    path: '/documents',
    emptyTitle: 'Select a thread',
    emptyHint: 'Pick a conversation from the sidebar, or start a new chat.',
    placeholder: 'Ask about a filing…',
  },
  email: {
    name: 'email',
    title: 'Email',
    description: 'Search your mail and AI newsletters, with citations to each message.',
    path: '/email',
    emptyTitle: 'Ask about your mail',
    emptyHint:
      'Start a new chat to search messages, check invoices, or see the big AI news of the week.',
    placeholder: 'Ask about your mail or AI news…',
  },
}
