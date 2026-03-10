import { sendEmail } from '@/lib/email/send'

// Mock Resend
const mockSend = jest.fn()
jest.mock('resend', () => ({
  Resend: jest.fn().mockImplementation(() => ({
    emails: { send: mockSend },
  })),
}))

// Mock nodemailer — use a shared mockSendMail fn created inside the factory
// to avoid TDZ issues with jest.mock hoisting
const mockSendMail = jest.fn()
const mockCreateTransport = jest.fn().mockReturnValue({ sendMail: mockSendMail })
jest.mock('nodemailer', () => {
  return {
    __esModule: true,
    default: {
      createTransport: (...args: unknown[]) => mockCreateTransport(...args),
    },
  }
})

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
      from: expect.stringContaining('noreply@rateshift.app'),
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
    ).rejects.toThrow('Failed to send email: Resend error: Invalid API key')
  })

  it('throws when no email provider is configured', async () => {
    // Clear the cached singleton by re-importing with reset modules
    jest.resetModules()
    process.env = { ...originalEnv }
    delete process.env.RESEND_API_KEY
    delete process.env.SMTP_HOST

    // Re-require after reset to get a fresh module with no cached _resend
    const { sendEmail: freshSendEmail } = require('@/lib/email/send')

    await expect(
      freshSendEmail({ to: 'user@example.com', subject: 'Test', html: '<p>Hi</p>' })
    ).rejects.toThrow('No email provider configured')
  })

  it('falls back to SMTP when Resend fails and SMTP is configured', async () => {
    process.env = {
      ...originalEnv,
      RESEND_API_KEY: 'test-api-key',
      SMTP_HOST: 'smtp.gmail.com',
      SMTP_PORT: '587',
      SMTP_USERNAME: 'user@gmail.com',
      SMTP_PASSWORD: 'app-password',
    }

    // Clear module cache so fresh env vars take effect for SMTP transporter
    jest.resetModules()
    const { sendEmail: freshSendEmail } = require('@/lib/email/send')

    mockSend.mockResolvedValueOnce({
      data: null,
      error: { message: 'Rate limited', name: 'rate_limit_error' },
    })
    mockSendMail.mockResolvedValueOnce({ messageId: 'smtp-123' })

    await freshSendEmail({
      to: 'user@example.com',
      subject: 'Fallback Test',
      html: '<p>Fallback</p>',
    })

    // Resend was attempted first
    expect(mockSend).toHaveBeenCalled()
    // SMTP fallback was used
    expect(mockSendMail).toHaveBeenCalledWith({
      from: expect.stringContaining('noreply@rateshift.app'),
      to: 'user@example.com',
      subject: 'Fallback Test',
      html: '<p>Fallback</p>',
    })
  })

  it('sends via SMTP directly when RESEND_API_KEY is absent', async () => {
    process.env = {
      ...originalEnv,
      SMTP_HOST: 'smtp.gmail.com',
      SMTP_PORT: '587',
      SMTP_USERNAME: 'user@gmail.com',
      SMTP_PASSWORD: 'app-password',
    }
    delete process.env.RESEND_API_KEY

    jest.resetModules()
    const { sendEmail: freshSendEmail } = require('@/lib/email/send')

    mockSendMail.mockResolvedValueOnce({ messageId: 'smtp-456' })

    await freshSendEmail({
      to: 'user@example.com',
      subject: 'SMTP Direct',
      html: '<p>Direct</p>',
    })

    // Resend was NOT called
    expect(mockSend).not.toHaveBeenCalled()
    // SMTP was used directly
    expect(mockSendMail).toHaveBeenCalledWith({
      from: expect.stringContaining('noreply@rateshift.app'),
      to: 'user@example.com',
      subject: 'SMTP Direct',
      html: '<p>Direct</p>',
    })
  })

  it('throws combined error when both providers fail', async () => {
    process.env = {
      ...originalEnv,
      RESEND_API_KEY: 'test-api-key',
      SMTP_HOST: 'smtp.gmail.com',
      SMTP_PORT: '587',
      SMTP_USERNAME: 'user@gmail.com',
      SMTP_PASSWORD: 'app-password',
    }

    jest.resetModules()
    const { sendEmail: freshSendEmail } = require('@/lib/email/send')

    mockSend.mockResolvedValueOnce({
      data: null,
      error: { message: 'Resend down', name: 'server_error' },
    })
    mockSendMail.mockRejectedValueOnce(new Error('SMTP connection refused'))

    await expect(
      freshSendEmail({ to: 'user@example.com', subject: 'Both Fail', html: '<p>Fail</p>' })
    ).rejects.toThrow('Failed to send email via both providers')
  })
})
