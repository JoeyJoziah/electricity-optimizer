import { Skeleton, ChartSkeleton } from '@/components/ui/skeleton'

export default function AnalyticsLoading() {
  return (
    <div className="flex flex-col">
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <Skeleton variant="text" className="h-8 w-40" />
        <Skeleton variant="text" className="mt-1 h-4 w-72" />
      </div>
      <div className="p-6 space-y-6">
        {/* State selector */}
        <Skeleton variant="rectangular" className="h-10 w-48" />
        {/* Widget grid */}
        <div className="grid gap-6 lg:grid-cols-2">
          <ChartSkeleton height={280} />
          <ChartSkeleton height={280} />
        </div>
        <Skeleton variant="rectangular" height={200} />
      </div>
    </div>
  )
}
