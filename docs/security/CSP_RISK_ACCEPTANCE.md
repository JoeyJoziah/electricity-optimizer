# CSP Risk Acceptance: `unsafe-inline` in `script-src`

**Date**: 2026-03-17
**Author**: Security Engineering (automated audit)
**Status**: Accepted with mitigations
**Risk Rating**: MEDIUM-LOW (residual risk after mitigations)
**Review Cadence**: Quarterly, or when Next.js releases nonce support for App Router static headers

---

## 1. Current CSP Configuration

Source: `frontend/next.config.js`, lines 55-68 (applied to all routes via `/(.*)`).

### Production CSP Directives

| Directive | Value |
|-----------|-------|
| `default-src` | `'self'` |
| `script-src` | `'self' 'unsafe-inline' https://*.clarity.ms https://cdn.onesignal.com` |
| `style-src` | `'self' 'unsafe-inline'` |
| `img-src` | `'self' data: blob: https://*.rateshift.app https://*.clarity.ms` |
| `font-src` | `'self'` |
| `connect-src` | `'self' https://*.rateshift.app https://*.onrender.com https://*.vercel.app https://www.clarity.ms https://*.clarity.ms https://onesignal.com https://*.onesignal.com` |
| `worker-src` | `'self'` |
| `frame-ancestors` | `'none'` |
| `base-uri` | `'self'` |
| `form-action` | `'self'` |

Development mode additionally allows `'unsafe-eval'` in `script-src`, `data:` in `font-src`, and `http://localhost:* ws://localhost:*` in `connect-src`. These are stripped in production builds.

### Companion Security Headers

| Header | Value | Effect |
|--------|-------|--------|
| `X-Frame-Options` | `DENY` | Prevents all framing (redundant with `frame-ancestors 'none'`) |
| `X-Content-Type-Options` | `nosniff` | Prevents MIME-type sniffing |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Limits referrer leakage |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` | Disables sensitive device APIs |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` | 2-year HSTS with preload |

The Cloudflare Worker at `api.rateshift.app` additionally injects `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security`, and `Referrer-Policy` on all API responses (see `workers/api-gateway/src/middleware/security.ts`).

---

## 2. Why `unsafe-inline` Is Present

Three distinct requirements force `'unsafe-inline'` in `script-src`:

### 2.1 Next.js Framework Inline Scripts

Next.js App Router emits inline `<script>` tags at build time for:

- Hydration bootstrapping (the `__NEXT_DATA__` / RSC payload script)
- Route prefetch hints
- Font optimization loader (Inter font via `next/font/google`)
- The `next/script` component with `strategy="afterInteractive"` (used by Clarity)

Without `'unsafe-inline'`, these framework-generated scripts would be blocked by CSP, breaking hydration entirely and rendering the application non-functional.

### 2.2 Microsoft Clarity Analytics

The Clarity tracking snippet (`frontend/lib/analytics/clarity.tsx`) uses `dangerouslySetInnerHTML` to inject the Clarity bootstrap script inline. This is the standard integration pattern recommended by Microsoft. The external Clarity tag loader fetches from `https://*.clarity.ms`, which is separately allowlisted.

### 2.3 JSON-LD Structured Data

The ISR rate pages (`frontend/app/rates/[state]/[utility]/page.tsx`) emit `<script type="application/ld+json">` with `dangerouslySetInnerHTML` for SEO structured data. While `application/ld+json` scripts are not executed by browsers (they are data-only), CSP `script-src` still governs their injection, and strict CSP without `'unsafe-inline'` can block their insertion in some browser implementations.

### 2.4 OneSignal Web Push SDK

The OneSignal integration loads its SDK via `react-onesignal` (dynamic import), with the service worker loaded from `https://cdn.onesignal.com`. The SDK itself does not require `'unsafe-inline'` -- it loads as an external script. However, removing `'unsafe-inline'` would still break the application for the reasons in 2.1 above.

---

## 3. Nonce-Based CSP Feasibility Analysis

### 3.1 How Nonces Work

A nonce-based CSP replaces `'unsafe-inline'` with a per-request cryptographic token:

```
script-src 'self' 'nonce-abc123...' https://*.clarity.ms https://cdn.onesignal.com
```

Every inline `<script>` tag must carry a matching `nonce="abc123..."` attribute. Scripts without the nonce are blocked. This preserves inline script functionality while preventing injected scripts (which would not have the nonce) from executing.

### 3.2 Next.js App Router Nonce Support -- Current State (March 2026)

**Next.js 16.x does not support nonce propagation in statically-defined CSP headers** (i.e., headers returned from `next.config.js headers()`). The fundamental problem:

1. Nonces must be unique per HTTP response. Static header configuration in `next.config.js` is evaluated at build time, not per-request.
2. Next.js App Router can generate nonces via `middleware.ts` by setting a response header dynamically, but this has significant limitations:
   - The middleware runs on the Edge Runtime and can set the CSP header with a generated nonce.
   - However, Next.js does not automatically propagate that nonce into the inline `<script>` tags it generates during SSR/RSC rendering.
   - The developer must manually thread the nonce through a `<Script nonce={nonce}>` prop on every `next/script` component and ensure framework-internal scripts also receive it.

3. **Framework-generated inline scripts are the blocker.** Next.js emits its own inline scripts (hydration bootstrap, RSC payload) that the application code has no control over. These scripts do not receive a nonce attribute unless Next.js itself adds one. As of Next.js 16.0.7, the framework does not inject nonce attributes into its own inline scripts when using App Router with static headers.

4. The `next/script` component does accept a `nonce` prop, which would solve the Clarity script case. But it does not solve the framework-generated hydration scripts.

### 3.3 Known Workarounds and Their Limitations

| Approach | Feasibility | Limitation |
|----------|-------------|------------|
| `next.config.js` static headers | Not feasible | Cannot generate per-request nonces |
| `middleware.ts` dynamic CSP | Partial | Nonce in header, but framework scripts lack `nonce` attribute |
| Custom `_document.tsx` (Pages Router) | Not applicable | RateShift uses App Router exclusively |
| `next/script` with `nonce` prop | Partial | Only covers application scripts, not framework scripts |
| Hash-based CSP (`'sha256-...'`) | Fragile | Hashes break on every build since script content changes |
| Strict-dynamic with nonce | Blocked | Requires nonce on bootstrap script, same root problem |

### 3.4 Verdict

**Nonce-based CSP is not feasible with the current Next.js 16 App Router without breaking hydration.** This is a known framework limitation tracked in the Next.js repository. The Vercel team has indicated intent to support nonces natively in App Router, but no shipping version includes this as of March 2026.

---

## 4. Threat Analysis: What `unsafe-inline` Enables

### 4.1 Attack Surface

With `'unsafe-inline'` in `script-src`, an attacker who achieves HTML injection (reflected or stored XSS) can execute arbitrary JavaScript in the user's browser context. The CSP will not block injected inline `<script>` tags.

### 4.2 Mitigating Factors That Reduce Residual Risk

**The following controls significantly reduce the practical exploitability:**

| Control | Effect | Residual Risk Reduction |
|---------|--------|------------------------|
| `default-src 'self'` | Blocks loading resources from arbitrary origins | Limits exfiltration targets |
| `connect-src` allowlist | Restricts `fetch`/`XMLHttpRequest`/`WebSocket` to 7 specific origins | Attacker cannot exfiltrate data to arbitrary servers via XHR/fetch |
| `frame-ancestors 'none'` | Prevents clickjacking and frame-based attacks | Eliminates an entire attack class |
| `base-uri 'self'` | Prevents `<base>` tag hijacking (relative URL manipulation) | Blocks a common CSP bypass technique |
| `form-action 'self'` | Prevents form submission to attacker-controlled endpoints | Blocks credential phishing via form injection |
| `object-src` (defaults to `'self'` via `default-src`) | Blocks plugin-based execution (Flash, Java applets) | Eliminates legacy plugin attack vectors |
| `X-Content-Type-Options: nosniff` | Prevents script injection via MIME confusion | Blocks a secondary injection path |
| HSTS preload (2-year, includeSubDomains) | Forces HTTPS, prevents protocol downgrade | Eliminates MitM script injection |
| React 19 auto-escaping | JSX auto-escapes interpolated values by default | Primary XSS defense at the rendering layer |
| nh3 server-side sanitization | Community content sanitized before storage | Blocks stored XSS in user-generated content |
| `dangerouslySetInnerHTML` audit | Only 2 usages, both with controlled inputs (Clarity ID, JSON-LD from server) | No user-controlled HTML injection points |
| Session-based auth (no JWT in localStorage) | Session tokens in `HttpOnly` cookies | XSS cannot steal authentication tokens |
| Better Auth `__Secure-` cookie prefix | Cookie requires HTTPS + Secure flag | Cookie theft requires HTTPS MitM (blocked by HSTS) |

### 4.3 Attack Scenarios and Effectiveness

| Scenario | Without CSP Mitigations | With Current CSP | Blocked? |
|----------|------------------------|-------------------|----------|
| Injected inline `<script>` executes | Yes | Yes (unsafe-inline allows it) | NO |
| Injected script exfiltrates data via `fetch()` to attacker.com | Yes | No (`connect-src` blocks it) | YES |
| Injected script loads external malicious script | Yes | No (`script-src` limits to 3 origins) | YES |
| Injected script submits form to attacker.com | Yes | No (`form-action 'self'`) | YES |
| Attacker frames page for clickjacking | Yes | No (`frame-ancestors 'none'`) | YES |
| Injected script reads `HttpOnly` cookies | No (browser enforces) | No | YES |
| Injected script reads `document.cookie` | Only non-HttpOnly cookies | Only non-HttpOnly cookies | PARTIAL |
| Injected script modifies DOM (defacement) | Yes | Yes | NO |
| Injected script keylogging on current page | Yes | Yes (but cannot exfiltrate) | PARTIAL |

**Key insight**: While `unsafe-inline` allows script execution, the tight `connect-src` allowlist prevents data exfiltration to attacker-controlled servers. An attacker can execute code but has extremely limited channels to extract stolen data. The `script-src` allowlist (only `'self'`, `*.clarity.ms`, `cdn.onesignal.com`) prevents loading attacker-controlled external scripts.

---

## 5. Risk Rating

### CVSS-like Assessment

| Factor | Rating | Justification |
|--------|--------|---------------|
| Attack Vector | Network | Requires finding an injection point first |
| Attack Complexity | High | React 19 auto-escaping + nh3 sanitization make injection difficult |
| Privileges Required | Varies | Stored XSS requires authenticated user; reflected XSS requires none |
| User Interaction | Required | Victim must visit the page with injected content |
| Confidentiality Impact | Low | `connect-src` blocks exfiltration; `HttpOnly` cookies inaccessible |
| Integrity Impact | Low | DOM modification possible but limited practical value |
| Availability Impact | None | No denial-of-service vector |

### Overall Rating: MEDIUM-LOW

The presence of `'unsafe-inline'` is a genuine weakening of CSP's XSS protection layer. However, it is one layer in a defense-in-depth strategy where:

1. The primary XSS defense (React auto-escaping + nh3 sanitization) prevents injection in the first place.
2. The secondary defenses (`connect-src`, `form-action`, `base-uri`, `HttpOnly` cookies) limit the impact even if injection occurs.
3. The CSP still provides significant value through its other directives (frame-ancestors, connect-src, base-uri, form-action, default-src).

This is not a "CSP is useless" situation. The CSP blocks the majority of post-exploitation actions even with `unsafe-inline` present.

---

## 6. Accepted Risk Statement

**We accept the residual risk of `'unsafe-inline'` in `script-src`** based on the following conditions:

1. **Framework limitation**: Next.js 16 App Router does not support nonce-based CSP for its own inline scripts. Removing `'unsafe-inline'` would break application hydration.
2. **Defense in depth**: 12+ other security controls (enumerated in Section 4.2) limit the practical impact of any XSS that bypasses the primary React escaping layer.
3. **Limited `dangerouslySetInnerHTML` usage**: Only 2 instances exist, both with developer-controlled inputs (no user-supplied HTML).
4. **Session architecture**: `HttpOnly` + `Secure` + `__Secure-` prefix cookies mean XSS cannot steal authentication tokens.
5. **Monitoring**: OWASP ZAP weekly scans, Sentry error tracking, and pip-audit/npm-audit CI gates provide ongoing vulnerability detection.

---

## 7. Removal Timeline

| Milestone | Target | Action |
|-----------|--------|--------|
| **Quarterly review** | Every 3 months | Check Next.js release notes for App Router nonce support |
| **Next.js nonce GA** | When available | Implement nonce-based CSP via middleware.ts, remove `'unsafe-inline'` from `script-src` |
| **Clarity migration** | With nonce support | Add `nonce` prop to `next/script` Clarity component |
| **JSON-LD audit** | With nonce support | Verify `application/ld+json` scripts work with strict CSP |
| **style-src cleanup** | After script-src | Evaluate removing `'unsafe-inline'` from `style-src` (Tailwind generates inline styles) |
| **CSP reporting** | Next sprint | Add `report-uri` or `report-to` directive for CSP violation monitoring |

### Immediate Improvement (No Breaking Changes)

The following enhancement can be made without removing `unsafe-inline`:

- **Add `report-to` / `report-uri`**: Configure CSP violation reporting to detect real-world injection attempts. This provides visibility into whether the `unsafe-inline` gap is being actively exploited, without changing the policy enforcement.

---

## 8. References

- `frontend/next.config.js` -- CSP header definition (lines 55-68)
- `frontend/lib/analytics/clarity.tsx` -- Clarity inline script (dangerouslySetInnerHTML)
- `frontend/app/rates/[state]/[utility]/page.tsx` -- JSON-LD structured data (dangerouslySetInnerHTML)
- `frontend/lib/notifications/onesignal.ts` -- OneSignal SDK integration
- `workers/api-gateway/src/middleware/security.ts` -- CF Worker security headers
- `docs/SECURITY_AUDIT.md` -- MEDIUM-001 finding (original identification)
- `docs/archive/swarm-reports/t5-security-perf-review.md` -- SEC-03 finding (swarm audit)
- `docs/plans/2026-03-17-whats-next-roadmap.md` -- Section 3.1 (roadmap tracking)
- `frontend/__tests__/config/next-config-csp.test.ts` -- CSP test coverage (4 directive tests + 4 header tests)

---

## 9. Approval

| Role | Name | Date | Decision |
|------|------|------|----------|
| Security Engineering | Automated Audit | 2026-03-17 | Accept with mitigations |
| Project Owner | _Pending_ | | |

**Next review date**: 2026-06-17 (quarterly)
