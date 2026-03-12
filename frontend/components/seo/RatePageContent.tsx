import Link from 'next/link'
import { US_STATES, UTILITY_TYPES, stateToSlug } from '@/lib/config/seo'

interface Breadcrumb {
  name: string
  url: string
}

interface SupplierEntry {
  supplier: string
  price: number | null
  rate_type?: string
  source?: string
  updated_at?: string | null
}

interface RateData {
  state: string
  utility_type: string
  unit: string
  average_price: number | null
  suppliers?: SupplierEntry[]
  prices?: { price: number | null; period_date?: string | null }[]
  count: number
}

interface RatePageContentProps {
  stateCode: string
  stateName: string
  utilityKey: string
  utilityLabel: string
  unit: string
  rateData: RateData | null
  breadcrumbs: Breadcrumb[]
}

export function RatePageContent({
  stateCode,
  stateName,
  utilityKey,
  utilityLabel,
  unit,
  rateData,
  breadcrumbs,
}: RatePageContentProps) {
  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      {/* Breadcrumbs */}
      <nav aria-label="Breadcrumb" className="mb-6 text-sm text-muted-foreground">
        {breadcrumbs.map((b, i) => (
          <span key={b.url}>
            {i > 0 && <span className="mx-1">/</span>}
            {i < breadcrumbs.length - 1 ? (
              <Link href={b.url} className="hover:underline">
                {b.name}
              </Link>
            ) : (
              <span>{b.name}</span>
            )}
          </span>
        ))}
      </nav>

      <h1 className="text-3xl font-bold">
        {utilityLabel} Rates in {stateName}
      </h1>
      <p className="mt-2 text-muted-foreground">
        Compare current {utilityLabel.toLowerCase()} rates and find the best deal in{' '}
        {stateName}.
      </p>

      {/* Average price card */}
      {rateData?.average_price != null && (
        <div className="mt-6 rounded-lg border bg-card p-6">
          <p className="text-sm text-muted-foreground">Average {utilityLabel} Rate</p>
          <p className="text-4xl font-bold">
            ${rateData.average_price.toFixed(4)}
            <span className="text-lg font-normal text-muted-foreground">/{unit}</span>
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Based on {rateData.count} data point{rateData.count !== 1 ? 's' : ''}
          </p>
        </div>
      )}

      {/* Supplier table */}
      {rateData?.suppliers && rateData.suppliers.length > 0 && (
        <section className="mt-8">
          <h2 className="text-xl font-semibold">Suppliers</h2>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="py-2 pr-4">Supplier</th>
                  <th className="py-2 pr-4">Rate (/{unit})</th>
                  <th className="py-2">Last Updated</th>
                </tr>
              </thead>
              <tbody>
                {rateData.suppliers.map((s, i) => (
                  <tr key={i} className="border-b">
                    <td className="py-2 pr-4">{s.supplier}</td>
                    <td className="py-2 pr-4">
                      {s.price != null ? `$${s.price.toFixed(4)}` : 'N/A'}
                    </td>
                    <td className="py-2 text-muted-foreground">
                      {s.updated_at
                        ? new Date(s.updated_at).toLocaleDateString()
                        : 'N/A'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Empty state */}
      {!rateData && (
        <div className="mt-8 rounded-lg border p-6 text-center">
          <p className="text-muted-foreground">
            No {utilityLabel.toLowerCase()} rate data available for {stateName} yet.
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            Check back soon — we update rates regularly.
          </p>
        </div>
      )}

      {/* Cross-links to other utilities */}
      <section className="mt-8">
        <h2 className="text-xl font-semibold">Other Utility Rates in {stateName}</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          {Object.entries(UTILITY_TYPES)
            .filter(([key]) => key !== utilityKey)
            .map(([key, val]) => (
              <Link
                key={key}
                href={`/rates/${stateToSlug(stateName)}/${val.slug}`}
                className="rounded-full border px-3 py-1 text-sm hover:bg-accent"
              >
                {val.label}
              </Link>
            ))}
        </div>
      </section>

      {/* Cross-links to nearby states */}
      <section className="mt-8">
        <h2 className="text-xl font-semibold">
          {utilityLabel} Rates in Nearby States
        </h2>
        <div className="mt-3 flex flex-wrap gap-2">
          {Object.entries(US_STATES)
            .filter(([code]) => code !== stateCode)
            .slice(0, 8)
            .map(([code, name]) => (
              <Link
                key={code}
                href={`/rates/${stateToSlug(name)}/${UTILITY_TYPES[utilityKey].slug}`}
                className="rounded-full border px-3 py-1 text-sm hover:bg-accent"
              >
                {name}
              </Link>
            ))}
        </div>
      </section>

      {/* CTA */}
      <section className="mt-8 rounded-lg bg-blue-50 p-6 text-center">
        <h2 className="text-lg font-semibold text-blue-900">
          Want personalized rate alerts?
        </h2>
        <p className="mt-1 text-sm text-blue-700">
          Sign up for RateShift to get notified when rates change in your area.
        </p>
        <Link
          href="/pricing"
          className="mt-3 inline-block rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Get Started Free
        </Link>
      </section>
    </main>
  )
}
