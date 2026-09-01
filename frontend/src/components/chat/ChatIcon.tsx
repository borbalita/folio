import { cn } from '@/lib/utils'

export function ChatIcon({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 overflow-hidden rounded-md bg-[#0B1F4A] p-0.5',
        className,
      )}
    >
      <img src="/robot-assistant.png" alt="" className="size-full object-contain" />
    </span>
  )
}
