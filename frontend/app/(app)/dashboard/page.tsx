import { Suspense } from "react";
import DashboardTabs from "@/components/dashboard/DashboardTabs";
import { ErrorBoundary } from "@/components/error-boundary";
import { Skeleton, ChartSkeleton } from "@/components/ui/skeleton";

export const metadata = { title: "Dashboard | RateShift" };

/** Shared skeleton shown by Suspense fallback — matches DashboardContent's loading state */
function DashboardSkeleton() {
  return (
    <div data-testid="dashboard-loading">
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <Skeleton variant="text" className="h-8 w-32" />
      </div>
      <div className="p-6">
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} variant="rectangular" height={120} />
          ))}
        </div>
        <div className="mt-6">
          <ChartSkeleton height={300} />
        </div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <ErrorBoundary>
      <Suspense fallback={<DashboardSkeleton />}>
        <DashboardTabs />
      </Suspense>
    </ErrorBoundary>
  );
}
