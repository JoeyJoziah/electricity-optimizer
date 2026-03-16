import { Skeleton } from '@/components/ui/skeleton'

export default function CommunityLoading() {
  return (
    <div className="flex flex-col">
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <Skeleton variant="text" className="h-8 w-32" />
      </div>
      <div className="p-6 space-y-4">
        <div className="flex items-center justify-between">
          <Skeleton variant="text" className="h-5 w-48" />
          <Skeleton variant="rectangular" className="h-9 w-28" />
        </div>
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="rounded-xl border border-gray-200 bg-white p-4 space-y-3"
          >
            <div className="flex items-center gap-3">
              <Skeleton variant="circular" width={32} height={32} />
              <div className="space-y-1 flex-1">
                <Skeleton variant="text" className="h-4 w-32" />
                <Skeleton variant="text" className="h-3 w-20" />
              </div>
            </div>
            <Skeleton variant="text" className="h-5 w-3/4" />
            <Skeleton variant="text" className="h-4 w-full" />
            <Skeleton variant="text" className="h-4 w-5/6" />
            <div className="flex gap-4 pt-1">
              <Skeleton variant="text" className="h-4 w-12" />
              <Skeleton variant="text" className="h-4 w-16" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
