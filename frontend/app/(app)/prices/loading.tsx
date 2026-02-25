import { Skeleton, ChartSkeleton } from '@/components/ui/skeleton'

export default function PricesLoading() {
  return (
    <div className="flex flex-col">
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <Skeleton variant="text" className="h-8 w-48" />
      </div>
      <div className="p-6">
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} variant="rectangular" height={120} />
          ))}
        </div>
        <div className="mt-6">
          <ChartSkeleton height={400} />
        </div>
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <Skeleton variant="rectangular" height={280} />
          <Skeleton variant="rectangular" height={280} />
        </div>
      </div>
    </div>
  )
}
