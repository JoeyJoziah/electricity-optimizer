'use client'

export function StatusBadge({ statusPageUrl }: { statusPageUrl: string }) {
  if (!statusPageUrl) return null
  return (
    <a
      href={statusPageUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1.5 text-xs text-neutral-500 hover:text-neutral-700 transition-colors"
    >
      <span className="h-2 w-2 rounded-full bg-success-500 animate-pulse" />
      System Status
    </a>
  )
}
