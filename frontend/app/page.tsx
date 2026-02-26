import Link from 'next/link'
import { Zap, TrendingDown, Bell, BarChart3, Shield, Clock } from 'lucide-react'

const features = [
  {
    icon: TrendingDown,
    title: 'Real-Time Price Tracking',
    description: 'Monitor electricity rates from local utility providers across all 50 states in real time.',
  },
  {
    icon: Bell,
    title: 'Smart Price Alerts',
    description: 'Get notified when rates drop below your threshold so you never miss a savings opportunity.',
  },
  {
    icon: BarChart3,
    title: 'ML-Powered Forecasts',
    description: 'Our machine learning models predict price movements 24 hours ahead with high accuracy.',
  },
  {
    icon: Clock,
    title: 'Schedule Optimization',
    description: 'Automatically schedule high-energy tasks during off-peak hours to maximize savings.',
  },
  {
    icon: Shield,
    title: 'GDPR Compliant',
    description: 'Your data is protected with enterprise-grade security and full regulatory compliance.',
  },
  {
    icon: Zap,
    title: 'Weather-Aware',
    description: 'Weather data integration improves forecast accuracy and helps plan energy usage.',
  },
]

const tiers = [
  {
    name: 'Free',
    price: '$0',
    period: '',
    description: 'Get started with basic price monitoring',
    features: ['Basic price view', '1 price alert', 'Manual scheduling', 'Local supplier comparison'],
    cta: 'Get Started',
    href: '/auth/signup',
    highlighted: false,
  },
  {
    name: 'Pro',
    price: '$4.99',
    period: '/mo',
    description: 'Everything you need to optimize your electricity costs',
    features: [
      'Unlimited price alerts',
      'ML-powered forecasts',
      'Smart schedule optimization',
      'Weather integration',
      'Historical price data',
      'Email notifications',
    ],
    cta: 'Start Free Trial',
    href: '/auth/signup?plan=pro',
    highlighted: true,
  },
  {
    name: 'Business',
    price: '$14.99',
    period: '/mo',
    description: 'For property managers and businesses',
    features: [
      'Everything in Pro',
      'API access',
      'Multi-property support',
      'Priority support',
      'Custom alert rules',
      'Advanced analytics',
    ],
    cta: 'Contact Sales',
    href: '/auth/signup?plan=business',
    highlighted: false,
  },
]

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-white">
      {/* Navigation */}
      <nav className="border-b border-gray-100">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2">
            <Zap className="h-8 w-8 text-blue-600" />
            <span className="text-xl font-bold text-gray-900">Electricity Optimizer</span>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/pricing" className="text-sm text-gray-600 hover:text-gray-900">
              Pricing
            </Link>
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

      {/* Hero */}
      <section className="px-4 pb-16 pt-20 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-4xl text-center">
          <h1 className="text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl md:text-6xl">
            Save Money on{' '}
            <span className="text-blue-600">Your Electricity Bills</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-gray-600">
            AI-powered price optimization that tracks real-time rates from local utility providers
            across all 50 states. Get smart alerts and ML forecasts to cut your electricity bill.
          </p>
          <div className="mt-10 flex items-center justify-center gap-4">
            <Link
              href="/auth/signup"
              className="rounded-lg bg-blue-600 px-6 py-3 text-base font-medium text-white shadow-sm hover:bg-blue-700"
            >
              Start Saving Today
            </Link>
            <Link
              href="/dashboard"
              className="rounded-lg border border-gray-300 px-6 py-3 text-base font-medium text-gray-700 hover:bg-gray-50"
            >
              View Demo
            </Link>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="bg-gray-50 px-4 py-20 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="text-center">
            <h2 className="text-3xl font-bold text-gray-900">
              Everything you need to optimize energy costs
            </h2>
            <p className="mt-4 text-lg text-gray-600">
              Powered by real NREL data and machine learning
            </p>
          </div>
          <div className="mt-16 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {features.map((feature) => (
              <div key={feature.title} className="rounded-xl bg-white p-6 shadow-sm">
                <feature.icon className="h-8 w-8 text-blue-600" />
                <h3 className="mt-4 text-lg font-semibold text-gray-900">{feature.title}</h3>
                <p className="mt-2 text-sm text-gray-600">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing Preview */}
      <section className="px-4 py-20 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="text-center">
            <h2 className="text-3xl font-bold text-gray-900">Simple, transparent pricing</h2>
            <p className="mt-4 text-lg text-gray-600">
              Start free. Upgrade when you need more.
            </p>
          </div>
          <div className="mt-16 grid gap-8 lg:grid-cols-3">
            {tiers.map((tier) => (
              <div
                key={tier.name}
                className={`rounded-xl border p-8 ${
                  tier.highlighted
                    ? 'border-blue-600 ring-2 ring-blue-600'
                    : 'border-gray-200'
                }`}
              >
                <h3 className="text-lg font-semibold text-gray-900">{tier.name}</h3>
                <p className="mt-2 text-sm text-gray-600">{tier.description}</p>
                <div className="mt-4">
                  <span className="text-4xl font-bold text-gray-900">{tier.price}</span>
                  <span className="text-gray-600">{tier.period}</span>
                </div>
                <ul className="mt-6 space-y-3">
                  {tier.features.map((feature) => (
                    <li key={feature} className="flex items-start gap-2 text-sm text-gray-600">
                      <span className="mt-0.5 text-blue-600">&#10003;</span>
                      {feature}
                    </li>
                  ))}
                </ul>
                <Link
                  href={tier.href}
                  className={`mt-8 block rounded-lg px-4 py-2 text-center text-sm font-medium ${
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
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-200 bg-gray-50 px-4 py-12 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
            <div className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-blue-600" />
              <span className="font-semibold text-gray-900">Electricity Optimizer</span>
            </div>
            <div className="flex gap-6 text-sm text-gray-600">
              <Link href="/pricing" className="hover:text-gray-900">Pricing</Link>
              <Link href="/privacy" className="hover:text-gray-900">Privacy</Link>
              <Link href="/terms" className="hover:text-gray-900">Terms</Link>
            </div>
            <p className="text-sm text-gray-500">
              &copy; {new Date().getFullYear()} Electricity Optimizer. All rights reserved.
            </p>
          </div>
        </div>
      </footer>
    </div>
  )
}
