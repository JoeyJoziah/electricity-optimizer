import { AnalyticsDashboard } from '@/components/analytics/AnalyticsDashboard'
import { ErrorBoundary } from '@/components/error-boundary'

export const metadata = { title: 'Premium Analytics | RateShift' }

export default function AnalyticsPage() {
  return (
    <div className="flex flex-col">
      <div className="border-b px-6 py-4">
        <h1 className="text-xl font-semibold text-gray-900">
          Premium Analytics
        </h1>
        <p className="text-sm text-gray-500">
          Rate forecasts, spend optimization, and data export across all utility types
        </p>
      </div>
      <div className="p-6">
        <ErrorBoundary>
          <AnalyticsDashboard />
        </ErrorBoundary>
      </div>
    </div>
  )
}
