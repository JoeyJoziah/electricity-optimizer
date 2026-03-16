import { Skeleton } from '@/components/ui/skeleton'

export default function CommunitySolarLoading() {
  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div>
        <Skeleton variant="text" className="h-8 w-48" />
        <Skeleton variant="text" className="mt-1 h-4 w-80" />
      </div>
      {/* Savings calculator */}
      <div className="rounded-lg border border-gray-200 bg-white p-5 space-y-4">
        <Skeleton variant="text" className="h-6 w-44" />
        <div className="flex gap-3">
          <Skeleton variant="rectangular" className="h-10 w-32" />
          <Skeleton variant="rectangular" className="h-10 w-24" />
          <Skeleton variant="rectangular" className="h-10 w-24" />
        </div>
      </div>
      {/* State coverage */}
      <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-3">
        <Skeleton variant="text" className="h-6 w-52" />
        <div className="flex flex-wrap gap-2">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Skeleton key={i} variant="text" className="h-6 w-14" />
          ))}
        </div>
      </div>
      {/* Filter */}
      <div className="flex gap-2">
        <Skeleton variant="text" className="h-7 w-10" />
        <Skeleton variant="text" className="h-7 w-16" />
        <Skeleton variant="text" className="h-7 w-16" />
      </div>
      {/* Program cards */}
      {[1, 2, 3].map((i) => (
        <Skeleton key={i} variant="rectangular" height={140} />
      ))}
    </div>
  )
}
