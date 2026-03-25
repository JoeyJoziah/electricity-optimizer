import { Skeleton } from "@/components/ui/skeleton";

export default function PrivacyLoading() {
  return (
    <div className="min-h-screen bg-white">
      {/* Navigation skeleton */}
      <nav className="border-b border-gray-100">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <Skeleton variant="text" className="h-8 w-32" />
        </div>
      </nav>

      {/* Content skeleton */}
      <main className="mx-auto max-w-3xl px-4 py-16 sm:px-6 lg:px-8">
        <Skeleton variant="text" className="h-9 w-56" />
        <Skeleton variant="text" className="mt-2 h-4 w-48" />

        <div className="mt-8 space-y-8">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
            <div key={i}>
              <Skeleton variant="text" className="h-6 w-64" />
              <div className="mt-3 space-y-2">
                <Skeleton variant="text" className="h-4 w-full" />
                <Skeleton variant="text" className="h-4 w-full" />
                <Skeleton variant="text" className="h-4 w-3/4" />
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
