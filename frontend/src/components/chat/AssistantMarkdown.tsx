import { Children, isValidElement, useMemo, type ReactNode } from 'react'
import type { Components } from 'react-markdown'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { CitationMark } from '@/components/chat/CitationMark'

const ALLOWED_ELEMENTS = [
  'p',
  'ul',
  'ol',
  'li',
  'strong',
  'em',
  'code',
  'a',
  'table',
  'thead',
  'tbody',
  'tr',
  'th',
  'td',
]

const MARK_RE = /\[(\d+)\]/g

function MarkdownCode({ children }: { children?: ReactNode }) {
  return <code className="rounded bg-background px-1 text-[0.85em]">{children}</code>
}

interface CitationHandlers {
  indexes: ReadonlySet<number>
  selectedIndex: number | null
  onSelect: (citationIndex: number) => void
}

function plainText(node: ReactNode): string | null {
  if (typeof node === 'string' || typeof node === 'number') {
    return String(node)
  }
  if (Array.isArray(node)) {
    const parts = node.map(plainText)
    if (parts.some((part) => part === null)) {
      return null
    }
    return parts.join('')
  }
  return null
}

function citationIndexFromAnchor(
  href: string | undefined,
  children: ReactNode,
  indexes: ReadonlySet<number>,
): number | null {
  if (href) {
    const fromHref = /^#cite-(\d+)$/.exec(href)
    if (fromHref) {
      const index = Number(fromHref[1])
      return indexes.has(index) ? index : null
    }
    return null
  }
  const text = plainText(children)?.trim()
  if (!text) {
    return null
  }
  const wrapped = /^\[(\d+)\]$/.exec(text)
  const bare = /^(\d+)$/.exec(text)
  const raw = wrapped?.[1] ?? bare?.[1]
  if (raw === undefined) {
    return null
  }
  const index = Number(raw)
  return indexes.has(index) ? index : null
}

function wrapText(text: string, handlers: CitationHandlers): ReactNode {
  const { indexes, selectedIndex, onSelect } = handlers
  const nodes: ReactNode[] = []
  let last = 0
  const pattern = new RegExp(MARK_RE.source, 'g')
  let match: RegExpExecArray | null
  while ((match = pattern.exec(text)) !== null) {
    const index = Number(match[1])
    if (!indexes.has(index)) {
      continue
    }
    if (match.index > last) {
      nodes.push(text.slice(last, match.index))
    }
    nodes.push(
      <CitationMark
        key={`cite-${match.index}-${index}`}
        index={index}
        selected={selectedIndex === index}
        onSelect={onSelect}
      />,
    )
    last = match.index + match[0].length
  }
  if (nodes.length === 0) {
    return text
  }
  if (last < text.length) {
    nodes.push(text.slice(last))
  }
  return nodes
}

function injectCitationMarks(node: ReactNode, handlers: CitationHandlers): ReactNode {
  return Children.map(node, (child) => {
    if (typeof child === 'string') {
      return wrapText(child, handlers)
    }
    if (!isValidElement(child)) {
      return child
    }
    if (child.type !== 'a') {
      return child
    }
    const props = child.props as { href?: string; children?: ReactNode }
    const index = citationIndexFromAnchor(props.href, props.children, handlers.indexes)
    if (index !== null) {
      return (
        <CitationMark
          index={index}
          selected={handlers.selectedIndex === index}
          onSelect={handlers.onSelect}
        />
      )
    }
    return props.children ?? null
  })
}

function markdownComponents(handlers: CitationHandlers): Components {
  const text = (children: ReactNode) => injectCitationMarks(children, handlers)
  return {
    p: ({ children }) => <p className="leading-relaxed">{text(children)}</p>,
    ul: ({ children }) => <ul className="list-disc space-y-1 pl-4">{text(children)}</ul>,
    ol: ({ children }) => (
      <ol className="list-decimal space-y-1 pl-4">{text(children)}</ol>
    ),
    li: ({ children }) => <li className="leading-relaxed">{text(children)}</li>,
    strong: ({ children }) => <strong className="font-semibold">{text(children)}</strong>,
    em: ({ children }) => <em>{text(children)}</em>,
    code: MarkdownCode,
    a: ({ href, children }) => {
      const index = citationIndexFromAnchor(href, children, handlers.indexes)
      if (index !== null) {
        return (
          <CitationMark
            index={index}
            selected={handlers.selectedIndex === index}
            onSelect={handlers.onSelect}
          />
        )
      }
      return <>{children}</>
    },
    table: ({ children }) => (
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-xs">{text(children)}</table>
      </div>
    ),
    thead: ({ children }) => <thead className="bg-background">{text(children)}</thead>,
    tbody: ({ children }) => <tbody>{text(children)}</tbody>,
    tr: ({ children }) => (
      <tr className="border-b border-border">{text(children)}</tr>
    ),
    th: ({ children }) => (
      <th className="px-2 py-1 text-left font-medium">{text(children)}</th>
    ),
    td: ({ children }) => <td className="px-2 py-1">{text(children)}</td>,
  }
}

interface AssistantMarkdownProps {
  children: string
  citationIndexes: readonly number[]
  selectedIndex: number | null
  onSelect: (citationIndex: number) => void
}

export function AssistantMarkdown({
  children,
  citationIndexes,
  selectedIndex,
  onSelect,
}: AssistantMarkdownProps) {
  const indexes = useMemo(() => new Set(citationIndexes), [citationIndexes])
  const components = useMemo(
    () => markdownComponents({ indexes, selectedIndex, onSelect }),
    [indexes, selectedIndex, onSelect],
  )

  return (
    <div className="space-y-2">
      <Markdown
        remarkPlugins={[remarkGfm]}
        allowedElements={ALLOWED_ELEMENTS}
        unwrapDisallowed
        components={components}
      >
        {children}
      </Markdown>
    </div>
  )
}
