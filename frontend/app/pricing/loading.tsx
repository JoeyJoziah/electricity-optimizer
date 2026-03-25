import { Skeleton } from "@/components/ui/skeleton";

export default function PricingLoading() {
  return (
    <div className="min-h-screen bg-white">
      {/* Navigation skeleton */}
      <nav className="border-b border-gray-100">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <Skeleton variant="text" className="h-8 w-32" />
          <div className="flex items-center gap-4">
            <Skeleton variant="text" className="h-4 w-16" />
            <Skeleton variant="rectangular" className="h-9 w-24 rounded-lg" />
          </div>
        </div>
      </nav>

      {/* Header skeleton */}
      <section className="px-4 pb-8 pt-16 text-center sm:px-6 lg:px-8">
        <Skeleton variant="text" className="mx-auto h-10 w-80" />
        <Skeleton variant="text" className="mx-auto mt-4 h-5 w-96" />
      </section>

      {/* Pricing cards skeleton */}
      <section className="px-4 pb-20 sm:px-6 lg:px-8">
        <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="flex flex-col rounded-xl border border-gray-200 p-8"
            >
              <Skeleton variant="text" className="h-6 w-16" />
              <Skeleton variant="text" className="mt-2 h-4 w-48" />
              <Skeleton variant="text" className="mt-6 h-12 w-24" />
              <div className="mt-8 flex-1 space-y-3">
                {[1, 2, 3, 4, 5].map((j) => (
                  <Skeleton key={j} variant="text" className="h-4 w-full" />
                ))}
              </div>
              <Skeleton
                variant="rectangular"
                className="mt-8 h-12 w-full rounded-lg"
              />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
