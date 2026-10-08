import type { AgentName } from '@/lib/api'

export interface AgentInfo {
  name: AgentName
  title: string
  description: string
  path: string
  emptyTitle: string
  emptyHint: string
  placeholder: string
  /** False for agents that open a workspace instead of a chat thread. */
  hasThreads: boolean
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
    hasThreads: true,
  },
  email: {
    name: 'email',
    title: 'Email Assistant',
    description: 'Search your mail and AI newsletters, with citations to each message.',
    path: '/email',
    emptyTitle: 'Ask about your mail',
    emptyHint:
      'Start a new chat to search messages or see the big AI news of the week.',
    placeholder: 'Ask about your mail or AI news…',
    hasThreads: true,
  },
  finance: {
    name: 'finance',
    title: 'Finance',
    description: 'Invoices, transactions and accounts in one place.',
    path: '/finance',
    emptyTitle: 'Nothing here yet',
    emptyHint: 'Finance is just getting started.',
    placeholder: 'Ask about your finances…',
    hasThreads: false,
  },
}
