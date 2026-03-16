import PricesContent from '@/components/prices/PricesContent'
import { ErrorBoundary } from '@/components/error-boundary'

export const metadata = { title: 'Electricity Prices | RateShift' }

export default function PricesPage() {
  return (
    <ErrorBoundary>
      <PricesContent />
    </ErrorBoundary>
  )
}
