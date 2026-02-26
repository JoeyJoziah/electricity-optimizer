import type { Metadata } from 'next'
import Link from 'next/link'
import { Zap } from 'lucide-react'

export const metadata: Metadata = {
  title: 'Terms of Service',
  description: 'Electricity Optimizer terms of service.',
}

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-white">
      <nav className="border-b border-gray-100">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <Link href="/" className="flex items-center gap-2">
            <Zap className="h-8 w-8 text-blue-600" />
            <span className="text-xl font-bold text-gray-900">Electricity Optimizer</span>
          </Link>
        </div>
      </nav>

      <main className="mx-auto max-w-3xl px-4 py-16 sm:px-6 lg:px-8">
        <h1 className="text-3xl font-bold text-gray-900">Terms of Service</h1>
        <p className="mt-2 text-sm text-gray-500">Last updated: February 12, 2026</p>

        <div className="prose prose-gray mt-8 max-w-none">
          <h2 className="text-xl font-semibold text-gray-900 mt-8">1. Acceptance of Terms</h2>
          <p className="mt-3 text-gray-600">
            By accessing or using Electricity Optimizer, you agree to be bound by these
            Terms of Service. If you do not agree, please do not use the service.
          </p>

          <h2 className="text-xl font-semibold text-gray-900 mt-8">2. Service Description</h2>
          <p className="mt-3 text-gray-600">
            Electricity Optimizer provides AI-powered electricity price monitoring, forecasting,
            and optimization tools for US consumers across all 50 states. Our service uses data from NREL,
            EIA, and other sources to help users make informed decisions about electricity usage.
          </p>

          <h2 className="text-xl font-semibold text-gray-900 mt-8">3. Disclaimer</h2>
          <p className="mt-3 text-gray-600">
            Price forecasts and optimization recommendations are provided for informational
            purposes only. We do not guarantee the accuracy of predictions or savings estimates.
            Actual electricity costs depend on your provider, usage patterns, and market conditions.
          </p>

          <h2 className="text-xl font-semibold text-gray-900 mt-8">4. Subscription and Billing</h2>
          <p className="mt-3 text-gray-600">
            Paid plans (Pro and Business) are billed monthly through Stripe. You may cancel
            at any time; access continues until the end of the current billing period.
            Refunds are handled on a case-by-case basis.
          </p>

          <h2 className="text-xl font-semibold text-gray-900 mt-8">5. User Accounts</h2>
          <p className="mt-3 text-gray-600">
            You are responsible for maintaining the security of your account credentials.
            You must provide accurate information when creating an account. One account per person.
          </p>

          <h2 className="text-xl font-semibold text-gray-900 mt-8">6. Acceptable Use</h2>
          <p className="mt-3 text-gray-600">
            You agree not to misuse the service, including but not limited to: attempting to
            circumvent rate limits, scraping data, reverse engineering the ML models, or
            using the service for any illegal purpose.
          </p>

          <h2 className="text-xl font-semibold text-gray-900 mt-8">7. API Usage (Business Tier)</h2>
          <p className="mt-3 text-gray-600">
            Business tier API access is subject to rate limits. API keys are confidential
            and must not be shared. We reserve the right to revoke API access for misuse.
          </p>

          <h2 className="text-xl font-semibold text-gray-900 mt-8">8. Limitation of Liability</h2>
          <p className="mt-3 text-gray-600">
            Electricity Optimizer is provided &quot;as is&quot; without warranty of any kind.
            We are not liable for any direct, indirect, incidental, or consequential damages
            arising from use of the service, including any financial decisions made based
            on our data or recommendations.
          </p>

          <h2 className="text-xl font-semibold text-gray-900 mt-8">9. Changes to Terms</h2>
          <p className="mt-3 text-gray-600">
            We may update these terms from time to time. Continued use of the service
            after changes constitutes acceptance of the updated terms.
          </p>

          <h2 className="text-xl font-semibold text-gray-900 mt-8">10. Contact</h2>
          <p className="mt-3 text-gray-600">
            For questions about these terms, contact us at legal@electricity-optimizer.com.
          </p>
        </div>
      </main>

      <footer className="border-t border-gray-200 px-4 py-8 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-blue-600" />
            <span className="font-semibold text-gray-900">Electricity Optimizer</span>
          </div>
          <div className="flex gap-6 text-sm text-gray-600">
            <Link href="/" className="hover:text-gray-900">Home</Link>
            <Link href="/pricing" className="hover:text-gray-900">Pricing</Link>
            <Link href="/privacy" className="hover:text-gray-900">Privacy</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
