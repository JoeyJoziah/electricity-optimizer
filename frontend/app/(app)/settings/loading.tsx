import { Skeleton } from '@/components/ui/skeleton'

export default function SettingsLoading() {
  return (
    <div className="flex flex-col">
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <Skeleton variant="text" className="h-8 w-24" />
      </div>
      <div className="p-6 space-y-6">
        {/* Section blocks */}
        {[1, 2, 3].map((section) => (
          <div
            key={section}
            className="rounded-xl border border-gray-200 bg-white p-6 space-y-4"
          >
            <Skeleton variant="text" className="h-6 w-40" />
            <div className="space-y-3">
              {[1, 2, 3].map((row) => (
                <div key={row} className="flex items-center justify-between">
                  <div className="space-y-1 flex-1 mr-8">
                    <Skeleton variant="text" className="h-4 w-32" />
                    <Skeleton variant="text" className="h-3 w-56" />
                  </div>
                  <Skeleton variant="rectangular" className="h-9 w-40" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
