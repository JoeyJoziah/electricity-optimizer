import { Skeleton, ChartSkeleton } from '@/components/ui/skeleton'

export default function HeatingOilLoading() {
  return (
    <div className="flex flex-col">
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <Skeleton variant="text" className="h-8 w-44" />
        <Skeleton variant="text" className="mt-1 h-4 w-72" />
      </div>
      <div className="p-6 space-y-6">
        {/* Stats cards */}
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} variant="rectangular" height={120} />
          ))}
        </div>
        {/* Price chart */}
        <ChartSkeleton height={280} />
        {/* Dealer list */}
        <div className="space-y-3">
          <Skeleton variant="text" className="h-6 w-32" />
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} variant="rectangular" height={80} />
          ))}
        </div>
      </div>
    </div>
  )
}
