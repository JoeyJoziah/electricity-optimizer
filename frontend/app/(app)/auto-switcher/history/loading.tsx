import { Skeleton } from "@/components/ui/skeleton";

export default function SwitchHistoryLoading() {
  return (
    <div className="flex flex-col">
      {/* Header skeleton */}
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <Skeleton variant="text" className="h-8 w-36" />
      </div>

      <div className="p-4 lg:p-6">
        {/* Back link + description skeleton */}
        <div className="mb-6 space-y-2">
          <Skeleton variant="text" className="h-4 w-48" />
          <Skeleton variant="text" className="h-4 w-80" />
        </div>

        {/* Timeline skeleton */}
        <div className="relative">
          {/* Vertical line */}
          <div
            className="absolute left-4 top-0 bottom-0 w-px bg-gray-200 sm:left-5"
            aria-hidden="true"
          />

          <div className="space-y-4 pl-10 sm:pl-12">
            {/* Date group label */}
            <Skeleton variant="text" className="h-3 w-20" />

            {/* Card skeletons */}
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="rounded-xl border border-gray-200 bg-white p-5 space-y-3"
              >
                {/* Status row */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Skeleton variant="circular" className="h-4 w-4" />
                    <Skeleton variant="text" className="h-4 w-36" />
                  </div>
                  <Skeleton variant="text" className="h-5 w-16 rounded-full" />
                </div>

                {/* Plan transition */}
                <div className="flex items-center gap-2">
                  <Skeleton variant="text" className="h-5 w-32" />
                  <Skeleton variant="text" className="h-4 w-4" />
                  <Skeleton variant="text" className="h-5 w-32" />
                </div>

                {/* Savings */}
                <div className="flex items-center gap-4">
                  <Skeleton variant="text" className="h-4 w-24" />
                  <Skeleton variant="text" className="h-4 w-20" />
                </div>

                {/* Expand toggle */}
                <div className="border-t border-gray-100 pt-3">
                  <Skeleton variant="text" className="h-3 w-28" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
