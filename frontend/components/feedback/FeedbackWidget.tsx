'use client'

import React, { useState, useCallback, useRef, useEffect } from 'react'
import { MessageSquarePlus, X, Send, CheckCircle, AlertCircle, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import { Button } from '@/components/ui/button'

type FeedbackType = 'bug' | 'feature' | 'general'

interface FeedbackPayload {
  type: FeedbackType
  message: string
}

const TYPE_OPTIONS: { value: FeedbackType; label: string; description: string }[] = [
  { value: 'bug', label: 'Bug Report', description: 'Something is broken or not working as expected' },
  { value: 'feature', label: 'Feature Request', description: 'Suggest a new feature or improvement' },
  { value: 'general', label: 'General Feedback', description: 'Share any thoughts or comments' },
]

async function submitFeedback(payload: FeedbackPayload): Promise<{ id: string }> {
  const res = await fetch('/api/v1/feedback', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body?.detail ?? `Request failed with status ${res.status}`)
  }
  return res.json()
}

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------

interface FeedbackModalProps {
  onClose: () => void
}

function FeedbackModal({ onClose }: FeedbackModalProps) {
  const [type, setType] = useState<FeedbackType>('general')
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const modalRef = useRef<HTMLDivElement>(null)
  const firstFocusRef = useRef<HTMLButtonElement>(null)

  // Focus trap + close on Escape
  useEffect(() => {
    firstFocusRef.current?.focus()

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault()
      if (!message.trim() || message.trim().length < 10) {
        setError('Please enter at least 10 characters.')
        return
      }
      setError(null)
      setSubmitting(true)
      try {
        await submitFeedback({ type, message: message.trim() })
        setSubmitted(true)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Submission failed. Please try again.')
      } finally {
        setSubmitting(false)
      }
    },
    [type, message]
  )

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="feedback-modal-title"
      className="fixed inset-0 z-50 flex items-end justify-end p-4 sm:items-end sm:justify-end"
      data-testid="feedback-modal"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/20 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        ref={modalRef}
        className={cn(
          'relative w-full max-w-sm rounded-xl bg-white shadow-card',
          'border border-gray-200',
          'animate-slide-up',
          'mb-16' // sits above the FAB
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
          <h2
            id="feedback-modal-title"
            className="text-base font-semibold text-gray-900"
          >
            Send Feedback
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
            aria-label="Close feedback form"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {submitted ? (
          /* Success state */
          <div
            className="flex flex-col items-center gap-3 px-5 py-8 text-center"
            data-testid="feedback-success"
          >
            <CheckCircle className="h-10 w-10 text-success-500" />
            <p className="text-base font-medium text-gray-900">Thank you!</p>
            <p className="text-sm text-gray-500">
              Your feedback has been received. We read every submission.
            </p>
            <Button variant="outline" size="sm" onClick={onClose} className="mt-2">
              Close
            </Button>
          </div>
        ) : (
          /* Form */
          <form onSubmit={handleSubmit} className="px-5 py-4 space-y-4" noValidate>
            {/* Type selector */}
            <fieldset>
              <legend className="mb-2 block text-sm font-medium text-gray-700">
                Feedback type
              </legend>
              <div className="space-y-2">
                {TYPE_OPTIONS.map((opt, index) => (
                  <label
                    key={opt.value}
                    className={cn(
                      'flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors',
                      type === opt.value
                        ? 'border-primary-400 bg-primary-50'
                        : 'border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50'
                    )}
                  >
                    <input
                      ref={index === 0 ? firstFocusRef as React.RefObject<HTMLInputElement> : undefined}
                      type="radio"
                      name="feedback-type"
                      value={opt.value}
                      checked={type === opt.value}
                      onChange={() => setType(opt.value)}
                      className="mt-0.5 h-4 w-4 shrink-0 text-primary-600 focus:ring-primary-500"
                    />
                    <div>
                      <span className="block text-sm font-medium text-gray-900">
                        {opt.label}
                      </span>
                      <span className="block text-xs text-gray-500">{opt.description}</span>
                    </div>
                  </label>
                ))}
              </div>
            </fieldset>

            {/* Message */}
            <div>
              <label
                htmlFor="feedback-message"
                className="mb-1.5 block text-sm font-medium text-gray-700"
              >
                Message
              </label>
              <textarea
                id="feedback-message"
                value={message}
                onChange={(e) => {
                  setMessage(e.target.value)
                  if (error) setError(null)
                }}
                rows={4}
                maxLength={5000}
                placeholder="Tell us more... (minimum 10 characters)"
                className={cn(
                  'block w-full rounded-lg border bg-white px-4 py-2.5',
                  'text-gray-900 placeholder-gray-400 text-sm',
                  'focus:outline-none focus:ring-2 focus:ring-offset-0',
                  'transition-all duration-200 resize-none',
                  'hover:border-gray-400',
                  error
                    ? 'border-danger-300 focus:border-danger-500 focus:ring-danger-500'
                    : 'border-gray-300 focus:border-primary-500 focus:ring-primary-500'
                )}
                aria-describedby={error ? 'feedback-message-error' : 'feedback-message-hint'}
                data-testid="feedback-message"
              />
              {error ? (
                <p
                  id="feedback-message-error"
                  className="mt-1.5 flex items-center gap-1 text-sm text-danger-600"
                  role="alert"
                  data-testid="feedback-error"
                >
                  <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                  {error}
                </p>
              ) : (
                <p id="feedback-message-hint" className="mt-1 text-xs text-gray-400">
                  {message.length}/5000 characters
                </p>
              )}
            </div>

            {/* Submit */}
            <Button
              type="submit"
              variant="primary"
              className="w-full"
              disabled={submitting}
              data-testid="feedback-submit"
            >
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              {submitting ? 'Sending...' : 'Send Feedback'}
            </Button>
          </form>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// FeedbackWidget (floating action button + modal)
// ---------------------------------------------------------------------------

export function FeedbackWidget() {
  const [open, setOpen] = useState(false)

  const handleOpen = useCallback(() => setOpen(true), [])
  const handleClose = useCallback(() => setOpen(false), [])

  return (
    <>
      {/* Floating action button */}
      <button
        onClick={handleOpen}
        aria-label="Open feedback form"
        data-testid="feedback-fab"
        className={cn(
          'fixed bottom-6 right-6 z-40',
          'flex items-center gap-2 rounded-full px-4 py-3',
          'bg-primary-600 text-white shadow-lg',
          'hover:bg-primary-700 active:scale-95',
          'transition-all duration-200',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2'
        )}
      >
        <MessageSquarePlus className="h-5 w-5" />
        <span className="text-sm font-medium hidden sm:inline">Feedback</span>
      </button>

      {/* Modal */}
      {open && <FeedbackModal onClose={handleClose} />}
    </>
  )
}
