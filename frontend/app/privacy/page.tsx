import type { Metadata } from 'next'
import Link from 'next/link'
import { Zap } from 'lucide-react'

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description: 'Electricity Optimizer privacy policy - how we handle your data.',
}

export default function PrivacyPage() {
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
        <h1 className="text-3xl font-bold text-gray-900">Privacy Policy</h1>
        <p className="mt-2 text-sm text-gray-500">Last updated: February 12, 2026</p>

        <div className="prose prose-gray mt-8 max-w-none">
          <h2 className="text-xl font-semibold text-gray-900 mt-8">1. Information We Collect</h2>
          <p className="mt-3 text-gray-600">
            We collect information you provide when creating an account (email, name) and usage
            data such as price alerts you configure and optimization preferences. We also collect
            electricity consumption data you choose to share for personalized recommendations.
          </p>

          <h2 className="text-xl font-semibold text-gray-900 mt-8">2. How We Use Your Information</h2>
          <p className="mt-3 text-gray-600">
            Your data is used to provide and improve our electricity optimization services,
            including price alerts, ML-powered forecasts, and scheduling recommendations.
            We do not sell your personal data to third parties.
          </p>

          <h2 className="text-xl font-semibold text-gray-900 mt-8">3. Data Storage and Security</h2>
          <p className="mt-3 text-gray-600">
            Your data is stored on secure servers (Neon PostgreSQL) with encryption at rest
            and in transit. We follow industry best practices for data security including
            JWT authentication, rate limiting, and regular security audits.
          </p>

          <h2 className="text-xl font-semibold text-gray-900 mt-8">4. GDPR Compliance</h2>
          <p className="mt-3 text-gray-600">
            We are committed to GDPR compliance. You have the right to access, correct, or
            delete your personal data at any time. We maintain consent records and honor
            data deletion requests within 30 days. Data residency is in the US.
          </p>

          <h2 className="text-xl font-semibold text-gray-900 mt-8">5. Third-Party Services</h2>
          <p className="mt-3 text-gray-600">
            We use the following third-party services: NREL for electricity price data,
            OpenWeatherMap for weather data, Stripe for payment processing, and SendGrid
            for email notifications. Each service has its own privacy policy.
          </p>

          <h2 className="text-xl font-semibold text-gray-900 mt-8">6. Cookies</h2>
          <p className="mt-3 text-gray-600">
            We use essential cookies for authentication and session management. No
            tracking cookies are used without your explicit consent.
          </p>

          <h2 className="text-xl font-semibold text-gray-900 mt-8">7. Data Retention</h2>
          <p className="mt-3 text-gray-600">
            We retain your data for up to 730 days (2 years) after your last activity.
            You can request deletion of your account and all associated data at any time.
          </p>

          <h2 className="text-xl font-semibold text-gray-900 mt-8">8. Contact</h2>
          <p className="mt-3 text-gray-600">
            For privacy-related inquiries, please contact us at privacy@electricity-optimizer.com.
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
            <Link href="/terms" className="hover:text-gray-900">Terms</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
