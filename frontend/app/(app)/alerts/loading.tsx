import { Skeleton } from '@/components/ui/skeleton'

export default function AlertsLoading() {
  return (
    <div className="flex flex-col">
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <Skeleton variant="text" className="h-8 w-24" />
      </div>
      <div className="p-6 space-y-4">
        <div className="flex items-center justify-between">
          <Skeleton variant="text" className="h-5 w-40" />
          <Skeleton variant="rectangular" className="h-9 w-32" />
        </div>
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="rounded-xl border border-gray-200 bg-white p-4 space-y-2"
          >
            <div className="flex items-center justify-between">
              <Skeleton variant="text" className="h-5 w-48" />
              <Skeleton variant="text" className="h-4 w-16" />
            </div>
            <Skeleton variant="text" className="h-4 w-full" />
            <Skeleton variant="text" className="h-4 w-3/4" />
          </div>
        ))}
      </div>
    </div>
  )
}
