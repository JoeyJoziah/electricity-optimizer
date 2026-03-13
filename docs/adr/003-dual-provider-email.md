# ADR-003: Dual-Provider Email System

**Status**: Accepted
**Date**: 2026-03-01
**Decision Makers**: Devin McGrath

## Context

RateShift needs reliable email delivery for:
- Beta welcome emails
- Price alert notifications
- Dunning emails (payment failure recovery)
- Rate change alerts
- Account verification

A single email provider creates a single point of failure. Deliverability is critical for dunning (revenue recovery) and alerts (core value prop).

## Decision

Use **Resend** as primary email provider with **Gmail SMTP** as fallback.

- **Resend**: Domain `rateshift.app` verified, DKIM/SPF/DMARC configured, TLS enforced
- **Gmail SMTP**: Via nodemailer in frontend, fallback when Resend is unavailable
- **Sender**: `RateShift <noreply@rateshift.app>`
- **Domain ID**: `20c95ef2-42f4-4040-be75-2026e97e35c9`

## Consequences

### Positive
- High deliverability with proper DNS records (DKIM, SPF, DMARC)
- Automatic failover ensures emails always send
- Resend API is simple and developer-friendly
- Gmail SMTP requires no additional domain verification

### Negative
- Two email providers to monitor and maintain
- Gmail SMTP has lower sending limits (500/day)
- Email templates must work with both providers
- Resend costs scale with volume (free tier: 3,000 emails/month)
