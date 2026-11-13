import { FileText, Mail, Newspaper, Phone, Wallet, type LucideIcon } from 'lucide-react'

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
  icon: LucideIcon
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
    icon: FileText,
  },
  email: {
    name: 'email',
    title: 'Email Assistant',
    description: 'Search your mail, with citations to each message.',
    path: '/email',
    emptyTitle: 'Ask about your mail',
    emptyHint: 'Start a new chat to search your messages.',
    placeholder: 'Ask about your mail…',
    hasThreads: true,
    icon: Mail,
  },
  news: {
    name: 'news',
    title: 'AI News',
    description:
      'Every AI story from your newsletters by day, plus questions and briefings with citations.',
    path: '/news',
    emptyTitle: 'Ask about AI news',
    emptyHint:
      'Scan the stories on the dashboard, or start a new chat and ask "What were the big stories this week?" or "Catch me up since Monday".',
    placeholder: 'Ask about AI news…',
    hasThreads: true,
    icon: Newspaper,
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
    icon: Wallet,
  },
  phone: {
    name: 'phone',
    title: 'Phone',
    description: 'Talk out loud with a persona, like a phone call. A friend is ringing.',
    path: '/phone',
    emptyTitle: 'Who do you want to talk to?',
    emptyHint: 'Pick a persona to start a call.',
    placeholder: '',
    hasThreads: false,
    icon: Phone,
  },
}
