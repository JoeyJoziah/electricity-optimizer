'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export default function BetaSignupPage() {
  const [formData, setFormData] = useState({
    email: '',
    name: '',
    postcode: '',
    currentSupplier: '',
    monthlyBill: '',
    hearAbout: '',
  })
  const [submitted, setSubmitted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      const response = await fetch('/api/beta-signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      })

      if (!response.ok) {
        throw new Error('Signup failed')
      }

      setSubmitted(true)

      // Track signup event
      if (typeof window !== 'undefined' && (window as any).gtag) {
        (window as any).gtag('event', 'beta_signup', {
          event_category: 'engagement',
          event_label: formData.currentSupplier,
        })
      }
    } catch (err) {
      setError('Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  if (submitted) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 p-4">
        <Card className="max-w-md w-full">
          <CardHeader className="text-center">
            <div className="mx-auto mb-4 w-16 h-16 bg-green-100 rounded-full flex items-center justify-center">
              <svg className="w-8 h-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <CardTitle className="text-2xl">You're on the list! 🎉</CardTitle>
            <CardDescription className="text-base mt-2">
              Check your email for the next steps
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
              <p className="text-sm text-blue-900">
                <strong>What happens next:</strong>
              </p>
              <ol className="mt-2 text-sm text-blue-800 space-y-1 list-decimal list-inside">
                <li>You'll receive a welcome email within 24 hours</li>
                <li>Get your unique beta access code</li>
                <li>Start saving on your electricity bills!</li>
              </ol>
            </div>

            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
              <p className="text-sm text-yellow-900">
                <strong>💡 Beta Perks:</strong>
              </p>
              <ul className="mt-2 text-sm text-yellow-800 space-y-1 list-disc list-inside">
                <li>Lifetime 50% discount when we launch</li>
                <li>Priority support (24-hour response)</li>
                <li>Shape the product with your feedback</li>
              </ul>
            </div>

            <div className="text-center pt-4">
              <p className="text-sm text-gray-600">
                Questions? Email{' '}
                <a href="mailto:support@electricity-optimizer.app" className="text-blue-600 hover:underline">
                  support@electricity-optimizer.app
                </a>
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 p-4">
      <Card className="max-w-2xl w-full">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 w-16 h-16 bg-blue-600 rounded-full flex items-center justify-center">
            <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <CardTitle className="text-3xl">Join the Beta Program</CardTitle>
          <CardDescription className="text-base mt-2">
            Save $200+ per year on electricity bills with AI-powered optimization
          </CardDescription>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Personal Information */}
            <div className="space-y-4">
              <h3 className="font-semibold text-lg">Personal Information</h3>

              <div>
                <label htmlFor="email" className="block text-sm font-medium mb-2">
                  Email Address *
                </label>
                <Input
                  id="email"
                  type="email"
                  required
                  placeholder="you@example.com"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                />
              </div>

              <div>
                <label htmlFor="name" className="block text-sm font-medium mb-2">
                  Full Name *
                </label>
                <Input
                  id="name"
                  type="text"
                  required
                  placeholder="John Smith"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                />
              </div>

              <div>
                <label htmlFor="postcode" className="block text-sm font-medium mb-2">
                  ZIP Code *
                </label>
                <Input
                  id="postcode"
                  type="text"
                  required
                  placeholder="06510"
                  value={formData.postcode}
                  onChange={(e) => setFormData({ ...formData, postcode: e.target.value })}
                />
                <p className="text-xs text-gray-500 mt-1">
                  Used to find the best suppliers in your area
                </p>
              </div>
            </div>

            {/* Current Situation */}
            <div className="space-y-4">
              <h3 className="font-semibold text-lg">Current Electricity Setup</h3>

              <div>
                <label htmlFor="currentSupplier" className="block text-sm font-medium mb-2">
                  Current Supplier *
                </label>
                <select
                  id="currentSupplier"
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={formData.currentSupplier}
                  onChange={(e) => setFormData({ ...formData, currentSupplier: e.target.value })}
                >
                  <option value="">Select your supplier</option>
                  <option value="Eversource Energy">Eversource Energy</option>
                  <option value="United Illuminating">United Illuminating (UI)</option>
                  <option value="Town Utility">Town utility</option>
                  <option value="Other">Other</option>
                </select>
              </div>

              <div>
                <label htmlFor="monthlyBill" className="block text-sm font-medium mb-2">
                  Approximate Monthly Bill *
                </label>
                <select
                  id="monthlyBill"
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={formData.monthlyBill}
                  onChange={(e) => setFormData({ ...formData, monthlyBill: e.target.value })}
                >
                  <option value="">Select range</option>
                  <option value="<$75">Less than $75</option>
                  <option value="$75-$150">$75 - $150</option>
                  <option value="$150-$225">$150 - $225</option>
                  <option value="$225-$300">$225 - $300</option>
                  <option value=">$300">More than $300</option>
                </select>
              </div>

              <div>
                <label htmlFor="hearAbout" className="block text-sm font-medium mb-2">
                  How did you hear about us? *
                </label>
                <select
                  id="hearAbout"
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={formData.hearAbout}
                  onChange={(e) => setFormData({ ...formData, hearAbout: e.target.value })}
                >
                  <option value="">Select one</option>
                  <option value="Twitter">Twitter</option>
                  <option value="LinkedIn">LinkedIn</option>
                  <option value="Reddit">Reddit</option>
                  <option value="Friend">Friend or colleague</option>
                  <option value="Search">Google search</option>
                  <option value="Other">Other</option>
                </select>
              </div>
            </div>

            {/* Beta Agreement */}
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
              <div className="flex items-start">
                <input
                  type="checkbox"
                  id="agree"
                  required
                  className="mt-1 mr-3"
                />
                <label htmlFor="agree" className="text-sm text-gray-700">
                  I agree to participate in the beta program, provide feedback, and understand this is
                  a testing phase. I've read the{' '}
                  <a href="/privacy" className="text-blue-600 hover:underline">Privacy Policy</a>
                  {' '}and{' '}
                  <a href="/terms" className="text-blue-600 hover:underline">Terms of Service</a>.
                </label>
              </div>
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-800">
                {error}
              </div>
            )}

            <Button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white py-3 text-lg"
            >
              {loading ? 'Joining...' : 'Join Beta Program →'}
            </Button>

            <p className="text-xs text-center text-gray-500">
              We'll never share your information with third parties. You can unsubscribe anytime.
            </p>
          </form>

          {/* Benefits Section */}
          <div className="mt-8 pt-8 border-t border-gray-200">
            <h3 className="font-semibold text-lg mb-4 text-center">What You'll Get</h3>
            <div className="grid md:grid-cols-3 gap-4">
              <div className="text-center p-4">
                <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-2">
                  <span className="text-2xl">💰</span>
                </div>
                <h4 className="font-medium mb-1">Save Money</h4>
                <p className="text-sm text-gray-600">
                  $200+ average annual savings
                </p>
              </div>

              <div className="text-center p-4">
                <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-2">
                  <span className="text-2xl">🤖</span>
                </div>
                <h4 className="font-medium mb-1">AI-Powered</h4>
                <p className="text-sm text-gray-600">
                  24-hour price forecasting
                </p>
              </div>

              <div className="text-center p-4">
                <div className="w-12 h-12 bg-purple-100 rounded-full flex items-center justify-center mx-auto mb-2">
                  <span className="text-2xl">⚡</span>
                </div>
                <h4 className="font-medium mb-1">Auto-Switch</h4>
                <p className="text-sm text-gray-600">
                  Automatic supplier switching
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
