export function ChatEmptyState() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center">
      <h1 className="text-lg font-medium">Select a thread</h1>
      <p className="max-w-sm text-sm text-muted-foreground">
        Pick a conversation from the sidebar, or start a new chat.
      </p>
    </div>
  )
}
