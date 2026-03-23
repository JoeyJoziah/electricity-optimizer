/**
 * Email Sending Utility
 *
 * Uses Resend as the primary provider and nodemailer SMTP as a fallback.
 * Lazy-initializes clients to avoid build-time env var issues.
 *
 * Provider selection:
 *   1. Resend (RESEND_API_KEY) — tried first
 *   2. SMTP (SMTP_HOST + SMTP_USERNAME + SMTP_PASSWORD) — fallback
 *
 * Env vars:
 *   EMAIL_FROM_ADDRESS  — sender address shown to recipients
 *   RESEND_API_KEY      — Resend API key
 *   SMTP_HOST           — SMTP hostname (e.g. smtp.gmail.com)
 *   SMTP_PORT           — SMTP port, default 587
 *   SMTP_USERNAME       — SMTP login username
 *   SMTP_PASSWORD       — SMTP login password
 */

import "server-only";

import { Resend } from "resend";
import nodemailer from "nodemailer";

// ---------------------------------------------------------------------------
// Shared config
// ---------------------------------------------------------------------------

const FROM_ADDRESS =
  process.env.EMAIL_FROM_ADDRESS || "RateShift <noreply@rateshift.app>";

// ---------------------------------------------------------------------------
// Resend (primary)
// ---------------------------------------------------------------------------

let _resend: Resend | null = null;

function getResend(): Resend | null {
  if (_resend) return _resend;
  const apiKey = process.env.RESEND_API_KEY;
  if (!apiKey) return null;
  _resend = new Resend(apiKey);
  return _resend;
}

async function sendViaResend(
  to: string,
  subject: string,
  html: string,
): Promise<void> {
  const resend = getResend();
  if (!resend) {
    throw new Error("[Email] RESEND_API_KEY is not set");
  }
  const { data, error } = await resend.emails.send({
    from: FROM_ADDRESS,
    to,
    subject,
    html,
  });
  if (error) {
    throw new Error(`Resend error: ${error.message}`);
  }
  console.log(`[Email] Sent via Resend id=${data?.id}`);
}

// ---------------------------------------------------------------------------
// SMTP via nodemailer (fallback)
// ---------------------------------------------------------------------------

let _transporter: nodemailer.Transporter | null = null;

function getTransporter(): nodemailer.Transporter | null {
  if (_transporter) return _transporter;
  const host = process.env.SMTP_HOST;
  if (!host) return null;
  _transporter = nodemailer.createTransport({
    host,
    port: parseInt(process.env.SMTP_PORT ?? "587", 10),
    secure: false, // STARTTLS on port 587
    auth: {
      user: process.env.SMTP_USERNAME,
      pass: process.env.SMTP_PASSWORD,
    },
  });
  return _transporter;
}

async function sendViaSMTP(
  to: string,
  subject: string,
  html: string,
): Promise<void> {
  const transporter = getTransporter();
  if (!transporter) {
    throw new Error("[Email] SMTP_HOST is not set");
  }
  await transporter.sendMail({
    from: FROM_ADDRESS,
    to,
    subject,
    html,
  });
  console.log(`[Email] Sent via SMTP to=${to}`);
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

interface SendEmailParams {
  to: string;
  subject: string;
  html: string;
}

export async function sendEmail({
  to,
  subject,
  html,
}: SendEmailParams): Promise<void> {
  console.log(
    `[Email] Sending to=${to} subject="${subject}" from="${FROM_ADDRESS}"`,
  );

  // --- Try Resend first ---
  if (process.env.RESEND_API_KEY) {
    try {
      await sendViaResend(to, subject, html);
      return;
    } catch (resendErr) {
      const resendMsg =
        resendErr instanceof Error ? resendErr.message : String(resendErr);
      console.error(`[Email] Resend failed: ${resendMsg}`);

      // --- Fall back to SMTP ---
      if (process.env.SMTP_HOST) {
        try {
          await sendViaSMTP(to, subject, html);
          return;
        } catch (smtpErr) {
          const smtpMsg =
            smtpErr instanceof Error ? smtpErr.message : String(smtpErr);
          console.error(`[Email] SMTP fallback also failed: ${smtpMsg}`);
          throw new Error(
            `Failed to send email via both providers. Resend: ${resendMsg}. SMTP: ${smtpMsg}`,
          );
        }
      }

      // No SMTP configured — re-throw the Resend error
      throw new Error(`Failed to send email: ${resendMsg}`);
    }
  }

  // --- No Resend key — try SMTP directly ---
  if (process.env.SMTP_HOST) {
    try {
      await sendViaSMTP(to, subject, html);
      return;
    } catch (smtpErr) {
      const smtpMsg =
        smtpErr instanceof Error ? smtpErr.message : String(smtpErr);
      console.error(`[Email] SMTP failed: ${smtpMsg}`);
      throw new Error(`Failed to send email: ${smtpMsg}`);
    }
  }

  // No provider configured at all
  throw new Error(
    "[Email] No email provider configured. Set RESEND_API_KEY or SMTP_HOST.",
  );
}
