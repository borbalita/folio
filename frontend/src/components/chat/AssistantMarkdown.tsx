import type { Components } from 'react-markdown'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const ALLOWED_ELEMENTS = [
  'p',
  'ul',
  'ol',
  'li',
  'strong',
  'em',
  'code',
  'table',
  'thead',
  'tbody',
  'tr',
  'th',
  'td',
]

const components: Components = {
  p: ({ children }) => <p className="leading-relaxed">{children}</p>,
  ul: ({ children }) => <ul className="list-disc space-y-1 pl-4">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal space-y-1 pl-4">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }) => <em>{children}</em>,
  code: ({ children }) => (
    <code className="rounded bg-background px-1 text-[0.85em]">{children}</code>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-background">{children}</thead>,
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => <tr className="border-b border-border">{children}</tr>,
  th: ({ children }) => (
    <th className="px-2 py-1 text-left font-medium">{children}</th>
  ),
  td: ({ children }) => <td className="px-2 py-1">{children}</td>,
}

export function AssistantMarkdown({ children }: { children: string }) {
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
