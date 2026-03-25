import { Skeleton } from "@/components/ui/skeleton";

export default function RatePageLoading() {
  return (
    <div className="min-h-screen bg-white">
      {/* Breadcrumb skeleton */}
      <div className="border-b border-gray-100 px-4 py-3 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-7xl items-center gap-2">
          <Skeleton variant="text" className="h-4 w-12" />
          <Skeleton variant="text" className="h-4 w-4" />
          <Skeleton variant="text" className="h-4 w-12" />
          <Skeleton variant="text" className="h-4 w-4" />
          <Skeleton variant="text" className="h-4 w-24" />
          <Skeleton variant="text" className="h-4 w-4" />
          <Skeleton variant="text" className="h-4 w-20" />
        </div>
      </div>

      {/* Header skeleton */}
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <Skeleton variant="text" className="h-9 w-80" />
        <Skeleton variant="text" className="mt-2 h-5 w-96" />

        {/* Stats cards skeleton */}
        <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="rounded-xl border border-gray-200 bg-white p-4"
            >
              <Skeleton variant="text" className="h-4 w-24" />
              <Skeleton variant="text" className="mt-2 h-8 w-20" />
              <Skeleton variant="text" className="mt-1 h-3 w-16" />
            </div>
          ))}
        </div>

        {/* Supplier table skeleton */}
        <div className="mt-8 rounded-xl border border-gray-200 bg-white">
          <div className="border-b border-gray-200 px-6 py-4">
            <Skeleton variant="text" className="h-6 w-40" />
          </div>
          <div className="divide-y divide-gray-100">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="flex items-center gap-4 px-6 py-4">
                <Skeleton variant="text" className="h-4 w-40" />
                <Skeleton variant="text" className="h-4 w-20" />
                <Skeleton variant="text" className="h-4 w-24" />
                <Skeleton variant="text" className="h-4 w-16" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
