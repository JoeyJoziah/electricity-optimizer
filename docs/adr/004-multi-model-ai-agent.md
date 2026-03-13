# ADR-004: Multi-Model AI Agent

**Status**: Accepted
**Date**: 2026-03-11
**Decision Makers**: Devin McGrath

## Context

RateShift AI assistant needs to answer user questions about rates, suppliers, and savings. Requirements:
- Cost-effective (bootstrapped startup)
- Reliable (users expect responses)
- Streaming support (real-time UX)
- Tool use (lookup prices, compare suppliers)

Options considered: OpenAI GPT-4o, Anthropic Claude, Google Gemini, Groq, self-hosted.

## Decision

Use **Gemini 3 Flash Preview** as primary with **Groq Llama 3.3 70B** as fallback, plus **Composio** for tool integration.

- **Primary**: Gemini 3 Flash Preview (free tier: 10 RPM, 250 RPD)
- **Fallback**: Groq Llama 3.3 70B (triggered on 429 from Gemini)
- **Tools**: Composio (1K actions/month free tier) for price lookups, supplier comparison
- **Streaming**: SSE via `POST /agent/query`
- **Async**: `POST /agent/task` for long-running queries with polling

## Consequences

### Positive
- Zero LLM cost at current scale (both providers have free tiers)
- Automatic failover on 429 ensures reliability
- SSE streaming provides responsive UX
- Composio tools enable data-driven answers
- Per-tier rate limits (Free: 3/day, Pro: 20/day, Business: unlimited) align with monetization

### Negative
- Gemini free tier has strict rate limits (may hit 429 frequently at scale)
- Groq fallback uses different model (response quality may vary)
- Composio 1K action/month limit requires careful usage tracking
- Two LLM providers to monitor and maintain API keys
- Feature flag (`ENABLE_AI_AGENT`) needed for graceful disable
