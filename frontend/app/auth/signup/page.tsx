'use client'

/**
 * Signup Page
 */

import { SignupForm } from '@/components/auth/SignupForm'

export default function SignupPage() {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <h1 className="text-center text-3xl font-bold text-gray-900 mb-2">
          Electricity Optimizer
        </h1>
        <p className="text-center text-gray-600 mb-8">
          Create your account to start saving
        </p>
      </div>

      <SignupForm />
    </div>
  )
}
