import { Skeleton } from "@/components/ui/skeleton";

export default function ArchitectureLoading() {
  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Sidebar skeleton (diagram list) */}
      <div className="w-64 flex-shrink-0 border-r border-gray-200 bg-white p-4">
        <div className="mb-4 flex items-center justify-between">
          <Skeleton variant="text" className="h-5 w-24" />
          <Skeleton variant="rectangular" className="h-8 w-8 rounded" />
        </div>
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton
              key={i}
              variant="rectangular"
              className="h-10 w-full rounded"
            />
          ))}
        </div>
      </div>

      {/* Editor area skeleton */}
      <div className="flex-1 p-6">
        <div className="mb-4 flex items-center justify-between">
          <Skeleton variant="text" className="h-6 w-48" />
          <Skeleton variant="rectangular" className="h-9 w-20 rounded" />
        </div>
        <Skeleton
          variant="rectangular"
          className="h-[calc(100vh-12rem)] w-full rounded-lg"
        />
      </div>
    </div>
  );
}
