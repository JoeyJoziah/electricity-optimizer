import { Skeleton } from "@/components/ui/skeleton";

export default function AutoSwitcherLoading() {
  return (
    <div className="flex flex-col">
      {/* Header skeleton */}
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <Skeleton variant="text" className="h-8 w-36" />
      </div>

      <div className="p-4 lg:p-6 space-y-6">
        {/* Agent Status Card skeleton */}
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-4">
              <Skeleton
                variant="rectangular"
                className="h-12 w-12 rounded-xl"
              />
              <div className="space-y-2">
                <Skeleton variant="text" className="h-6 w-48" />
                <Skeleton variant="text" className="h-4 w-64" />
              </div>
            </div>
            <Skeleton variant="rectangular" className="h-10 w-32" />
          </div>
        </div>

        {/* Two-column card grid skeleton */}
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Current Plan card skeleton */}
          <div className="rounded-xl border border-gray-200 bg-white p-6">
            <Skeleton variant="text" className="mb-4 h-6 w-32" />
            <div className="space-y-3">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="flex items-center justify-between">
                  <Skeleton variant="text" className="h-4 w-24" />
                  <Skeleton variant="text" className="h-4 w-32" />
                </div>
              ))}
            </div>
          </div>

          {/* Recommendations card skeleton */}
          <div className="rounded-xl border border-gray-200 bg-white p-6">
            <Skeleton variant="text" className="mb-4 h-6 w-48" />
            <div className="space-y-3">
              {[1, 2].map((i) => (
                <div
                  key={i}
                  className="rounded-lg border border-gray-200 bg-gray-50 p-4 space-y-2"
                >
                  <Skeleton variant="text" className="h-4 w-3/4" />
                  <Skeleton variant="text" className="h-3 w-1/2" />
                  <div className="flex justify-end">
                    <Skeleton variant="rectangular" className="h-8 w-24" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Activity Feed skeleton */}
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <Skeleton variant="text" className="mb-4 h-6 w-36" />
          <div className="space-y-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="flex gap-3">
                <Skeleton variant="circular" className="h-8 w-8 shrink-0" />
                <div className="flex-1 space-y-1">
                  <Skeleton variant="text" className="h-4 w-3/4" />
                  <Skeleton variant="text" className="h-3 w-1/2" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
