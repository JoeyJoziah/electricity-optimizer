import { sendEmail } from '@/lib/email/send'

// Mock Resend
const mockSend = jest.fn()
jest.mock('resend', () => ({
  Resend: jest.fn().mockImplementation(() => ({
    emails: { send: mockSend },
  })),
}))

describe('sendEmail', () => {
  const originalEnv = process.env

  beforeEach(() => {
    jest.clearAllMocks()
    process.env = { ...originalEnv, RESEND_API_KEY: 'test-api-key' }
  })

  afterAll(() => {
    process.env = originalEnv
  })

  it('sends an email via Resend', async () => {
    mockSend.mockResolvedValueOnce({ data: { id: 'msg-123' }, error: null })

    await sendEmail({
      to: 'user@example.com',
      subject: 'Test Subject',
      html: '<p>Hello</p>',
    })

    expect(mockSend).toHaveBeenCalledWith({
      from: expect.stringContaining('noreply@electricity-optimizer.app'),
      to: 'user@example.com',
      subject: 'Test Subject',
      html: '<p>Hello</p>',
    })
  })

  it('throws when Resend returns an error', async () => {
    mockSend.mockResolvedValueOnce({
      data: null,
      error: { message: 'Invalid API key', name: 'validation_error' },
    })

    await expect(
      sendEmail({ to: 'user@example.com', subject: 'Test', html: '<p>Hi</p>' })
    ).rejects.toThrow('Failed to send email: Invalid API key')
  })

  it('throws when RESEND_API_KEY is not set', async () => {
    // Clear the cached singleton by re-importing with reset modules
    jest.resetModules()
    process.env = { ...originalEnv }
    delete process.env.RESEND_API_KEY

    // Re-require after reset to get a fresh module with no cached _resend
    const { sendEmail: freshSendEmail } = require('@/lib/email/send')

    await expect(
      freshSendEmail({ to: 'user@example.com', subject: 'Test', html: '<p>Hi</p>' })
    ).rejects.toThrow('RESEND_API_KEY is not set')
  })
})
