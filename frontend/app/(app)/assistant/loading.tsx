import { Skeleton } from '@/components/ui/skeleton'

export default function AssistantLoading() {
  return (
    <div className="flex flex-col">
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <Skeleton variant="text" className="h-8 w-36" />
      </div>
      <div className="flex flex-col p-6 space-y-4">
        {/* Chat message skeletons */}
        <div className="flex gap-3">
          <Skeleton variant="circular" width={36} height={36} />
          <div className="flex-1 space-y-2">
            <Skeleton variant="text" className="h-4 w-3/4" />
            <Skeleton variant="text" className="h-4 w-1/2" />
          </div>
        </div>
        <div className="flex gap-3 flex-row-reverse">
          <Skeleton variant="circular" width={36} height={36} />
          <div className="flex-1 space-y-2 flex flex-col items-end">
            <Skeleton variant="text" className="h-4 w-2/3" />
          </div>
        </div>
        <div className="flex gap-3">
          <Skeleton variant="circular" width={36} height={36} />
          <div className="flex-1 space-y-2">
            <Skeleton variant="text" className="h-4 w-full" />
            <Skeleton variant="text" className="h-4 w-5/6" />
            <Skeleton variant="text" className="h-4 w-2/3" />
          </div>
        </div>
        {/* Input bar */}
        <div className="mt-auto pt-6">
          <Skeleton variant="rectangular" className="h-12 w-full" />
        </div>
      </div>
    </div>
  )
}
