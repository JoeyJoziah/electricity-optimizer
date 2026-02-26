import { Skeleton, CardSkeleton } from '@/components/ui/skeleton'

export default function OptimizeLoading() {
  return (
    <div className="flex flex-col">
      {/* Header */}
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <Skeleton variant="text" className="h-8 w-44" />
      </div>

      <div className="p-6">
        {/* Stats row */}
        <div className="mb-6 grid gap-4 md:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} variant="rectangular" height={90} />
          ))}
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Appliances sidebar */}
          <div className="lg:col-span-1">
            <Skeleton variant="rectangular" height={460} />
          </div>

          {/* Schedule area */}
          <div className="lg:col-span-2 space-y-6">
            <Skeleton variant="rectangular" height={80} />
            <Skeleton variant="rectangular" height={280} />
          </div>
        </div>
      </div>
    </div>
  )
}
