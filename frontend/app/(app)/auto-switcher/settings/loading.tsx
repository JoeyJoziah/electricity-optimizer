import { Skeleton } from "@/components/ui/skeleton";

export default function AutoSwitcherSettingsLoading() {
  return (
    <div className="flex flex-col">
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <Skeleton variant="text" className="h-8 w-52" />
      </div>
      <div className="p-4 lg:p-6 space-y-6">
        {/* KillSwitch toggle skeleton */}
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <div className="flex items-center justify-between">
            <div className="space-y-2">
              <Skeleton variant="text" className="h-6 w-56" />
              <Skeleton variant="text" className="h-4 w-80" />
            </div>
            <Skeleton variant="rectangular" className="h-7 w-12 rounded-full" />
          </div>
        </div>

        {/* Savings threshold skeleton */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 space-y-4">
          <Skeleton variant="text" className="h-6 w-40" />
          <Skeleton variant="text" className="h-4 w-72" />
          <Skeleton variant="rectangular" className="h-10 w-full" />
          <Skeleton variant="rectangular" className="h-10 w-full" />
        </div>

        {/* Cooldown skeleton */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 space-y-4">
          <Skeleton variant="text" className="h-6 w-36" />
          <Skeleton variant="text" className="h-4 w-64" />
          <Skeleton variant="rectangular" className="h-10 w-48" />
        </div>

        {/* Pause until skeleton */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 space-y-4">
          <Skeleton variant="text" className="h-6 w-44" />
          <Skeleton variant="text" className="h-4 w-56" />
          <Skeleton variant="rectangular" className="h-10 w-48" />
        </div>

        {/* LOA skeleton */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 space-y-4">
          <Skeleton variant="text" className="h-6 w-48" />
          <Skeleton variant="text" className="h-4 w-full" />
          <Skeleton variant="rectangular" className="h-10 w-36" />
        </div>
      </div>
    </div>
  );
}
