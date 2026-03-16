import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom'

// JSDOM doesn't have scrollIntoView
Element.prototype.scrollIntoView = jest.fn()

// --- Mocks ---

const mockSendQuery = jest.fn()
const mockCancel = jest.fn()
const mockReset = jest.fn()

let mockMessages: Array<{
  role: string
  content: string
  model_used?: string
  tools_used?: string[]
  duration_ms?: number
}> = []
let mockIsStreaming = false
let mockError: string | null = null
let mockUsage: { used: number; limit: number; remaining: number } | undefined =
  undefined

jest.mock('@/lib/hooks/useAgent', () => ({
  useAgentQuery: () => ({
    messages: mockMessages,
    isStreaming: mockIsStreaming,
    error: mockError,
    sendQuery: mockSendQuery,
    cancel: mockCancel,
    reset: mockReset,
  }),
  useAgentStatus: () => ({
    data: mockUsage,
  }),
}))

import { AgentChat } from '@/components/agent/AgentChat'

describe('AgentChat', () => {
  beforeEach(() => {
    mockMessages = []
    mockIsStreaming = false
    mockError = null
    mockUsage = undefined
    jest.clearAllMocks()
  })

  it('renders empty state with example prompts', () => {
    render(<AgentChat />)

    expect(
      screen.getByText('How can I help you save on electricity?')
    ).toBeInTheDocument()
    expect(
      screen.getByText('What are the cheapest electricity rates in my area?')
    ).toBeInTheDocument()
    expect(
      screen.getByText('Compare my current supplier with alternatives')
    ).toBeInTheDocument()
  })

  it('renders header with title', () => {
    render(<AgentChat />)

    expect(screen.getByText('RateShift AI')).toBeInTheDocument()
    expect(screen.getByText('Energy savings assistant')).toBeInTheDocument()
  })

  it('renders input placeholder', () => {
    render(<AgentChat />)

    expect(
      screen.getByPlaceholderText('Ask RateShift AI...')
    ).toBeInTheDocument()
  })

  it('sends query when form is submitted', async () => {
    const user = userEvent.setup()
    render(<AgentChat />)

    const textarea = screen.getByPlaceholderText('Ask RateShift AI...')
    await user.type(textarea, 'Hello')
    await user.keyboard('{Enter}')

    expect(mockSendQuery).toHaveBeenCalledWith('Hello')
  })

  it('sends query when example prompt is clicked', async () => {
    const user = userEvent.setup()
    render(<AgentChat />)

    await user.click(
      screen.getByText('What are the cheapest electricity rates in my area?')
    )

    expect(mockSendQuery).toHaveBeenCalledWith(
      'What are the cheapest electricity rates in my area?'
    )
  })

  it('does not send empty query', async () => {
    const user = userEvent.setup()
    render(<AgentChat />)

    const textarea = screen.getByPlaceholderText('Ask RateShift AI...')
    await user.click(textarea)
    await user.keyboard('{Enter}')

    expect(mockSendQuery).not.toHaveBeenCalled()
  })

  it('renders messages when present', () => {
    mockMessages = [
      { role: 'user', content: 'What is my rate?' },
      {
        role: 'assistant',
        content: 'Your current rate is $0.18/kWh.',
        model_used: 'gemini-3-flash',
        duration_ms: 1200,
      },
    ]

    render(<AgentChat />)

    expect(screen.getByText('What is my rate?')).toBeInTheDocument()
    expect(
      screen.getByText('Your current rate is $0.18/kWh.')
    ).toBeInTheDocument()
    expect(screen.getByText(/via gemini-3-flash/)).toBeInTheDocument()
    expect(screen.getByText(/1.2s/)).toBeInTheDocument()
  })

  it('renders tool badges on assistant messages', () => {
    mockMessages = [
      {
        role: 'assistant',
        content: 'Here are your rates.',
        tools_used: ['get_rates', 'compare_suppliers'],
      },
    ]

    render(<AgentChat />)

    expect(screen.getByText('get_rates')).toBeInTheDocument()
    expect(screen.getByText('compare_suppliers')).toBeInTheDocument()
  })

  it('shows streaming indicator when streaming', () => {
    mockMessages = [{ role: 'user', content: 'Hi' }]
    mockIsStreaming = true

    render(<AgentChat />)

    expect(screen.getByText('Thinking...')).toBeInTheDocument()
  })

  it('shows cancel button when streaming', () => {
    mockIsStreaming = true

    render(<AgentChat />)

    const textarea = screen.getByPlaceholderText('Ask RateShift AI...')
    expect(textarea).toBeDisabled()
  })

  it('calls cancel when stop button is clicked', async () => {
    mockIsStreaming = true
    mockMessages = [{ role: 'user', content: 'Hi' }]

    const user = userEvent.setup()
    render(<AgentChat />)

    // Find the cancel button (type="button" vs type="submit")
    const buttons = screen.getAllByRole('button')
    const cancelBtn = buttons.find(
      (btn) => btn.getAttribute('type') === 'button'
    )
    if (cancelBtn) {
      await user.click(cancelBtn)
      expect(mockCancel).toHaveBeenCalled()
    }
  })

  it('shows error banner when error exists', () => {
    mockError = 'Rate limit exceeded'

    render(<AgentChat />)

    expect(screen.getByText('Rate limit exceeded')).toBeInTheDocument()
  })

  it('shows error message in chat for error role', () => {
    mockMessages = [
      { role: 'user', content: 'Hi' },
      { role: 'error', content: 'Something went wrong' },
    ]

    render(<AgentChat />)

    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
  })

  it('shows usage info when available', () => {
    mockUsage = { used: 5, limit: 20, remaining: 15 }

    render(<AgentChat />)

    expect(screen.getByText('5/20 queries today')).toBeInTheDocument()
  })

  it('shows unlimited usage format', () => {
    mockUsage = { used: 42, limit: -1, remaining: -1 }

    render(<AgentChat />)

    expect(screen.getByText('42 queries today')).toBeInTheDocument()
  })

  it('shows limit reached warning when remaining is 0', () => {
    mockUsage = { used: 3, limit: 3, remaining: 0 }

    render(<AgentChat />)

    expect(
      screen.getByText(/Daily query limit reached/)
    ).toBeInTheDocument()
  })

  it('shows reset button when messages exist', () => {
    mockMessages = [{ role: 'user', content: 'Hi' }]

    render(<AgentChat />)

    const resetButton = screen.getByTitle('New conversation')
    expect(resetButton).toBeInTheDocument()
  })

  it('calls reset when new conversation button is clicked', async () => {
    mockMessages = [{ role: 'user', content: 'Hi' }]
    const user = userEvent.setup()

    render(<AgentChat />)

    await user.click(screen.getByTitle('New conversation'))
    expect(mockReset).toHaveBeenCalled()
  })

  it('hides reset button when no messages', () => {
    render(<AgentChat />)

    expect(screen.queryByTitle('New conversation')).not.toBeInTheDocument()
  })

  it('shows character count', async () => {
    const user = userEvent.setup()
    render(<AgentChat />)

    expect(screen.getByText('0/2000')).toBeInTheDocument()

    const textarea = screen.getByPlaceholderText('Ask RateShift AI...')
    await user.type(textarea, 'Hello')

    expect(screen.getByText('5/2000')).toBeInTheDocument()
  })

  it('shows over-limit character count styling', () => {
    render(<AgentChat />)

    const textarea = screen.getByPlaceholderText('Ask RateShift AI...')
    fireEvent.change(textarea, { target: { value: 'a'.repeat(2001) } })

    expect(screen.getByText('2001/2000')).toBeInTheDocument()
  })
})
