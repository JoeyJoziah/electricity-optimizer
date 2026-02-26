import type { Metadata } from 'next'
import Link from 'next/link'
import { Zap, Check } from 'lucide-react'

export const metadata: Metadata = {
  title: 'Pricing',
  description: 'Electricity Optimizer pricing plans - Free, Pro, and Business tiers for US consumers.',
}

const tiers = [
  {
    name: 'Free',
    price: '$0',
    period: '',
    description: 'Get started with basic price monitoring',
    features: [
      'Real-time electricity prices',
      '1 price alert',
      'Manual schedule optimization',
      'Local supplier comparison',
      'Basic dashboard',
    ],
    limitations: ['No ML forecasts', 'No weather integration', 'No email notifications'],
    cta: 'Get Started Free',
    href: '/auth/signup',
    highlighted: false,
  },
  {
    name: 'Pro',
    price: '$4.99',
    period: '/mo',
    description: 'Everything you need to optimize your electricity costs',
    features: [
      'Everything in Free',
      'Unlimited price alerts',
      'ML-powered 24hr forecasts',
      'Smart schedule optimization',
      'Weather-aware predictions',
      'Historical price data',
      'Email notifications via SendGrid',
      'Savings tracker & gamification',
    ],
    limitations: [],
    cta: 'Start Free Trial',
    href: '/auth/signup?plan=pro',
    highlighted: true,
  },
  {
    name: 'Business',
    price: '$14.99',
    period: '/mo',
    description: 'For property managers and energy-intensive businesses',
    features: [
      'Everything in Pro',
      'REST API access',
      'Multi-property management',
      'Priority email support',
      'Custom alert rules & thresholds',
      'Advanced analytics & reporting',
      'SSE real-time streaming',
      'Dedicated account manager',
    ],
    limitations: [],
    cta: 'Contact Sales',
    href: '/auth/signup?plan=business',
    highlighted: false,
  },
]

export default function PricingPage() {
  return (
    <div className="min-h-screen bg-white">
      {/* Navigation */}
      <nav className="border-b border-gray-100">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <Link href="/" className="flex items-center gap-2">
            <Zap className="h-8 w-8 text-blue-600" />
            <span className="text-xl font-bold text-gray-900">Electricity Optimizer</span>
          </Link>
          <div className="flex items-center gap-4">
            <Link href="/auth/login" className="text-sm text-gray-600 hover:text-gray-900">
              Sign In
            </Link>
            <Link
              href="/auth/signup"
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              Get Started
            </Link>
          </div>
        </div>
      </nav>

      {/* Header */}
      <section className="px-4 pb-8 pt-16 text-center sm:px-6 lg:px-8">
        <h1 className="text-4xl font-bold text-gray-900">Simple, transparent pricing</h1>
        <p className="mt-4 text-lg text-gray-600">
          Start free. Upgrade when you&apos;re ready for ML forecasts and unlimited alerts.
        </p>
      </section>

      {/* Pricing Cards */}
      <section className="px-4 pb-20 sm:px-6 lg:px-8">
        <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-3">
          {tiers.map((tier) => (
            <div
              key={tier.name}
              className={`flex flex-col rounded-xl border p-8 ${
                tier.highlighted
                  ? 'border-blue-600 ring-2 ring-blue-600 shadow-lg'
                  : 'border-gray-200'
              }`}
            >
              {tier.highlighted && (
                <span className="mb-4 inline-block w-fit rounded-full bg-blue-100 px-3 py-1 text-xs font-medium text-blue-700">
                  Most Popular
                </span>
              )}
              <h2 className="text-xl font-bold text-gray-900">{tier.name}</h2>
              <p className="mt-2 text-sm text-gray-600">{tier.description}</p>
              <div className="mt-6">
                <span className="text-5xl font-bold text-gray-900">{tier.price}</span>
                <span className="text-lg text-gray-500">{tier.period}</span>
              </div>

              <ul className="mt-8 flex-1 space-y-3">
                {tier.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-2 text-sm text-gray-700">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-blue-600" />
                    {feature}
                  </li>
                ))}
                {tier.limitations.map((limitation) => (
                  <li key={limitation} className="flex items-start gap-2 text-sm text-gray-400">
                    <span className="mt-0.5 h-4 w-4 shrink-0 text-center">&mdash;</span>
                    {limitation}
                  </li>
                ))}
              </ul>

              <Link
                href={tier.href}
                className={`mt-8 block rounded-lg px-4 py-3 text-center text-sm font-medium ${
                  tier.highlighted
                    ? 'bg-blue-600 text-white hover:bg-blue-700'
                    : 'border border-gray-300 text-gray-700 hover:bg-gray-50'
                }`}
              >
                {tier.cta}
              </Link>
            </div>
          ))}
        </div>
      </section>

      {/* FAQ */}
      <section className="border-t border-gray-200 bg-gray-50 px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-3xl">
          <h2 className="text-2xl font-bold text-gray-900 text-center">Frequently asked questions</h2>
          <dl className="mt-10 space-y-8">
            <div>
              <dt className="font-semibold text-gray-900">Can I cancel anytime?</dt>
              <dd className="mt-2 text-sm text-gray-600">
                Yes. You can cancel your subscription at any time from your account settings.
                You&apos;ll continue to have access until the end of your billing period.
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-gray-900">What payment methods do you accept?</dt>
              <dd className="mt-2 text-sm text-gray-600">
                We accept all major credit cards through our secure Stripe payment system.
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-gray-900">Is my data secure?</dt>
              <dd className="mt-2 text-sm text-gray-600">
                Absolutely. We are fully GDPR compliant, use encrypted connections, and never sell your data.
                See our <Link href="/privacy" className="text-blue-600 underline">Privacy Policy</Link> for details.
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-gray-900">Where does the price data come from?</dt>
              <dd className="mt-2 text-sm text-gray-600">
                We use official NREL (National Renewable Energy Laboratory) and EIA data combined with real-time
                supplier feeds from utility providers across all 50 states.
              </dd>
            </div>
          </dl>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-200 px-4 py-8 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-blue-600" />
            <span className="font-semibold text-gray-900">Electricity Optimizer</span>
          </div>
          <div className="flex gap-6 text-sm text-gray-600">
            <Link href="/" className="hover:text-gray-900">Home</Link>
            <Link href="/privacy" className="hover:text-gray-900">Privacy</Link>
            <Link href="/terms" className="hover:text-gray-900">Terms</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
