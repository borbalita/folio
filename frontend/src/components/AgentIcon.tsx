import type { AgentInfo } from '@/lib/agents'
import { cn } from '@/lib/utils'

/** The agent's icon on a tinted tile. The robot (ChatIcon) stays the assistant's chat avatar. */
export function AgentIcon({ agent, className }: { agent: AgentInfo; className?: string }) {
  const Icon = agent.icon
  return (
    <span
      className={cn(
        'flex size-8 shrink-0 items-center justify-center rounded-md bg-ring/12 text-ring',
        className,
      )}
    >
      <Icon className="size-[55%]" aria-hidden />
    </span>
  )
}
