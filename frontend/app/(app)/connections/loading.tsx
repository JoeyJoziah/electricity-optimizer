import { Skeleton, CardSkeleton } from '@/components/ui/skeleton'

export default function ConnectionsLoading() {
  return (
    <div className="p-6 lg:p-8">
      <div className="mx-auto max-w-4xl">
        {/* Page header */}
        <div className="mb-8">
          <Skeleton variant="text" className="h-8 w-48" />
          <Skeleton variant="text" className="mt-2 h-4 w-80" />
        </div>

        {/* Tab bar */}
        <div className="mb-6 flex gap-4 border-b border-gray-200 pb-2">
          <Skeleton variant="text" className="h-5 w-28" />
          <Skeleton variant="text" className="h-5 w-20" />
        </div>

        {/* Connection cards */}
        <div className="space-y-4">
          <Skeleton variant="text" className="h-6 w-40" />
          <div className="space-y-3">
            {[1, 2].map((i) => (
              <Skeleton key={i} variant="rectangular" height={80} />
            ))}
          </div>
        </div>

        {/* Method picker */}
        <div className="mt-8 space-y-4">
          <Skeleton variant="text" className="h-6 w-48" />
          <div className="grid gap-4 sm:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} variant="rectangular" height={180} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
