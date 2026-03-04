/**
 * Email Sending Utility
 *
 * Uses Resend to send transactional emails (verification, magic links).
 * Lazy-initializes the Resend client to avoid build-time env var issues.
 */

import { Resend } from "resend"

let _resend: Resend | null = null

function getResend(): Resend {
  if (!_resend) {
    const apiKey = process.env.RESEND_API_KEY
    if (!apiKey) {
      throw new Error("[Email] RESEND_API_KEY is not set")
    }
    _resend = new Resend(apiKey)
  }
  return _resend
}

const FROM_ADDRESS =
  process.env.EMAIL_FROM_ADDRESS || "Electricity Optimizer <noreply@electricity-optimizer.app>"

interface SendEmailParams {
  to: string
  subject: string
  html: string
}

export async function sendEmail({ to, subject, html }: SendEmailParams): Promise<void> {
  const resend = getResend()
  const { error } = await resend.emails.send({
    from: FROM_ADDRESS,
    to,
    subject,
    html,
  })
  if (error) {
    console.error("[Email] Failed to send:", error)
    throw new Error(`Failed to send email: ${error.message}`)
  }
}
