import { Skeleton } from "@/components/ui/skeleton";

export default function DashboardLoading() {
  return (
    <div className="flex flex-col">
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <Skeleton variant="text" className="h-8 w-44" />
      </div>

      <div className="p-4 lg:p-6 space-y-6">
        {/* Stats row skeleton */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="rounded-xl border border-gray-200 bg-white p-5"
            >
              <Skeleton variant="text" className="mb-2 h-4 w-24" />
              <Skeleton variant="text" className="h-7 w-32" />
              <Skeleton variant="text" className="mt-1 h-3 w-20" />
            </div>
          ))}
        </div>

        {/* Two-column content skeleton */}
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="rounded-xl border border-gray-200 bg-white p-6">
            <Skeleton variant="text" className="mb-4 h-6 w-40" />
            <div className="h-48 space-y-3">
              {[1, 2, 3, 4].map((i) => (
                <Skeleton key={i} variant="text" className="h-4 w-full" />
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-gray-200 bg-white p-6">
            <Skeleton variant="text" className="mb-4 h-6 w-36" />
            <Skeleton
              variant="rectangular"
              className="h-48 w-full rounded-lg"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
