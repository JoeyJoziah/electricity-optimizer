import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom'
import React from 'react'

// ---------------------------------------------------------------------------
// Mock fetch
// ---------------------------------------------------------------------------

const mockFetch = jest.fn()
global.fetch = mockFetch

// ---------------------------------------------------------------------------
// Import after mocks
// ---------------------------------------------------------------------------

import { FeedbackWidget } from '@/components/feedback/FeedbackWidget'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockFetchSuccess() {
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({
      id: 'fb-test-id',
      type: 'general',
      status: 'new',
      created_at: '2026-03-10T12:00:00Z',
    }),
  })
}

function mockFetchError(status = 500, detail = 'Internal server error') {
  mockFetch.mockResolvedValue({
    ok: false,
    json: async () => ({ detail }),
    status,
  })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('FeedbackWidget', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  // --- FAB rendering ---

  it('renders the floating action button', () => {
    render(<FeedbackWidget />)
    expect(screen.getByTestId('feedback-fab')).toBeInTheDocument()
    expect(screen.getByLabelText('Open feedback form')).toBeInTheDocument()
  })

  it('does not show the modal before the FAB is clicked', () => {
    render(<FeedbackWidget />)
    expect(screen.queryByTestId('feedback-modal')).not.toBeInTheDocument()
  })

  // --- Modal open/close ---

  it('opens modal when FAB is clicked', async () => {
    const user = userEvent.setup()
    render(<FeedbackWidget />)

    await user.click(screen.getByTestId('feedback-fab'))

    expect(screen.getByTestId('feedback-modal')).toBeInTheDocument()
    expect(screen.getAllByText('Send Feedback').length).toBeGreaterThanOrEqual(1)
  })

  it('closes modal when close button is clicked', async () => {
    const user = userEvent.setup()
    render(<FeedbackWidget />)

    await user.click(screen.getByTestId('feedback-fab'))
    expect(screen.getByTestId('feedback-modal')).toBeInTheDocument()

    await user.click(screen.getByLabelText('Close feedback form'))
    expect(screen.queryByTestId('feedback-modal')).not.toBeInTheDocument()
  })

  it('closes modal when Escape key is pressed', async () => {
    const user = userEvent.setup()
    render(<FeedbackWidget />)

    await user.click(screen.getByTestId('feedback-fab'))
    expect(screen.getByTestId('feedback-modal')).toBeInTheDocument()

    await user.keyboard('{Escape}')
    expect(screen.queryByTestId('feedback-modal')).not.toBeInTheDocument()
  })

  it('closes modal when backdrop is clicked', async () => {
    const user = userEvent.setup()
    render(<FeedbackWidget />)

    await user.click(screen.getByTestId('feedback-fab'))
    expect(screen.getByTestId('feedback-modal')).toBeInTheDocument()

    // Click the backdrop (aria-hidden overlay div inside the modal).
    // Scope to the modal — document.querySelector would match lucide SVGs first.
    // Use fireEvent instead of userEvent — userEvent respects aria-hidden.
    const modal = screen.getByTestId('feedback-modal')
    const backdrop = modal.querySelector(':scope > [aria-hidden="true"]')
    expect(backdrop).not.toBeNull()
    fireEvent.click(backdrop as Element)

    expect(screen.queryByTestId('feedback-modal')).not.toBeInTheDocument()
  })

  // --- Form contents ---

  it('renders all three feedback type options', async () => {
    const user = userEvent.setup()
    render(<FeedbackWidget />)

    await user.click(screen.getByTestId('feedback-fab'))

    expect(screen.getByText('Bug Report')).toBeInTheDocument()
    expect(screen.getByText('Feature Request')).toBeInTheDocument()
    expect(screen.getByText('General Feedback')).toBeInTheDocument()
  })

  it('renders message textarea', async () => {
    const user = userEvent.setup()
    render(<FeedbackWidget />)

    await user.click(screen.getByTestId('feedback-fab'))

    expect(screen.getByTestId('feedback-message')).toBeInTheDocument()
  })

  it('renders submit button', async () => {
    const user = userEvent.setup()
    render(<FeedbackWidget />)

    await user.click(screen.getByTestId('feedback-fab'))

    expect(screen.getByTestId('feedback-submit')).toBeInTheDocument()
    expect(screen.getAllByText('Send Feedback').length).toBeGreaterThanOrEqual(1)
  })

  // --- Validation ---

  it('shows error when message is too short on submit', async () => {
    const user = userEvent.setup()
    render(<FeedbackWidget />)

    await user.click(screen.getByTestId('feedback-fab'))
    await user.type(screen.getByTestId('feedback-message'), 'Short')
    await user.click(screen.getByTestId('feedback-submit'))

    expect(screen.getByTestId('feedback-error')).toBeInTheDocument()
    expect(screen.getByText(/at least 10 characters/i)).toBeInTheDocument()
  })

  it('clears error when user starts typing again', async () => {
    const user = userEvent.setup()
    render(<FeedbackWidget />)

    await user.click(screen.getByTestId('feedback-fab'))

    // Trigger validation error
    await user.type(screen.getByTestId('feedback-message'), 'Short')
    await user.click(screen.getByTestId('feedback-submit'))
    expect(screen.getByTestId('feedback-error')).toBeInTheDocument()

    // Start typing again — error should clear
    await user.type(screen.getByTestId('feedback-message'), ' more text')
    expect(screen.queryByTestId('feedback-error')).not.toBeInTheDocument()
  })

  // --- Successful submission ---

  it('submits feedback and shows success state', async () => {
    mockFetchSuccess()
    const user = userEvent.setup()
    render(<FeedbackWidget />)

    await user.click(screen.getByTestId('feedback-fab'))
    await user.type(
      screen.getByTestId('feedback-message'),
      'This is a test feedback message that is long enough.'
    )
    await user.click(screen.getByTestId('feedback-submit'))

    await waitFor(() => {
      expect(screen.getByTestId('feedback-success')).toBeInTheDocument()
    })

    expect(screen.getByText('Thank you!')).toBeInTheDocument()
    expect(screen.getByText(/Your feedback has been received/i)).toBeInTheDocument()
  })

  it('calls POST /api/v1/feedback with correct payload', async () => {
    mockFetchSuccess()
    const user = userEvent.setup()
    render(<FeedbackWidget />)

    await user.click(screen.getByTestId('feedback-fab'))

    // Select "Bug Report" type
    const bugRadio = screen.getByDisplayValue('bug')
    await user.click(bugRadio)

    await user.type(
      screen.getByTestId('feedback-message'),
      'The chart fails to load on Safari 17.'
    )
    await user.click(screen.getByTestId('feedback-submit'))

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/feedback',
        expect.objectContaining({
          method: 'POST',
          credentials: 'include',
          headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({
            type: 'bug',
            message: 'The chart fails to load on Safari 17.',
          }),
        })
      )
    })
  })

  it('shows close button on success state that dismisses modal', async () => {
    mockFetchSuccess()
    const user = userEvent.setup()
    render(<FeedbackWidget />)

    await user.click(screen.getByTestId('feedback-fab'))
    await user.type(
      screen.getByTestId('feedback-message'),
      'This is a valid feedback message.'
    )
    await user.click(screen.getByTestId('feedback-submit'))

    await waitFor(() => {
      expect(screen.getByTestId('feedback-success')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Close'))
    expect(screen.queryByTestId('feedback-modal')).not.toBeInTheDocument()
  })

  // --- Error handling ---

  it('shows API error message when submission fails', async () => {
    mockFetchError(500, 'Internal server error')
    const user = userEvent.setup()
    render(<FeedbackWidget />)

    await user.click(screen.getByTestId('feedback-fab'))
    await user.type(
      screen.getByTestId('feedback-message'),
      'This message should trigger a server error.'
    )
    await user.click(screen.getByTestId('feedback-submit'))

    await waitFor(() => {
      expect(screen.getByTestId('feedback-error')).toBeInTheDocument()
    })

    expect(screen.getByText('Internal server error')).toBeInTheDocument()
    // Modal should remain open so user can retry
    expect(screen.getByTestId('feedback-modal')).toBeInTheDocument()
  })

  it('shows fallback error when fetch rejects entirely', async () => {
    mockFetch.mockRejectedValue(new TypeError('Failed to fetch'))
    const user = userEvent.setup()
    render(<FeedbackWidget />)

    await user.click(screen.getByTestId('feedback-fab'))
    await user.type(
      screen.getByTestId('feedback-message'),
      'This message will fail with a network error.'
    )
    await user.click(screen.getByTestId('feedback-submit'))

    await waitFor(() => {
      expect(screen.getByTestId('feedback-error')).toBeInTheDocument()
    })

    expect(screen.getByText('Failed to fetch')).toBeInTheDocument()
  })

  // --- Character counter ---

  it('shows character count hint', async () => {
    const user = userEvent.setup()
    render(<FeedbackWidget />)

    await user.click(screen.getByTestId('feedback-fab'))
    await user.type(screen.getByTestId('feedback-message'), 'Hello world')

    expect(screen.getByText(/11\/5000 characters/)).toBeInTheDocument()
  })
})
