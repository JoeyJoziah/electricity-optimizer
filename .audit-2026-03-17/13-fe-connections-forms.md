# 13 — Frontend: Connections & Forms Components

## Scope

Files audited (32 total):

**connections/**
- `ConnectionUploadFlow.tsx`
- `BillUploadTypes.ts`
- `BillUploadForm.tsx`
- `BillUploadFilePreview.tsx`
- `BillUploadDropZone.tsx`
- `BillUploadProgress.tsx`
- `BillUploadResults.tsx`
- `ExtractedField.tsx`
- `ConnectionMethodPicker.tsx`
- `ConnectionsOverview.tsx`
- `ConnectionCard.tsx`
- `ConnectionRates.tsx`
- `DirectLoginForm.tsx`
- `EmailConnectionFlow.tsx`
- `PortalConnectionFlow.tsx`
- `ConnectionAnalytics.tsx`
- `analytics/types.ts`
- `analytics/RateComparisonCard.tsx`
- `analytics/SavingsEstimateCard.tsx`
- `analytics/RateHistoryCard.tsx`
- `analytics/ConnectionHealthCard.tsx`
- `analytics/index.ts`

**community/**
- `PostForm.tsx`
- `PostList.tsx`
- `VoteButton.tsx`
- `ReportButton.tsx`
- `CommunityStats.tsx`

**community-solar/**
- `CommunitySolarContent.tsx`
- `SavingsCalculator.tsx`

**cca/**
- `CCAAlert.tsx`
- `CCAInfo.tsx`
- `CCAComparison.tsx`

---

## P0 — Critical

### 1. `EmailConnectionFlow.tsx` — Unauthenticated `connected` query-param injection (open-redirect equivalent)

**File:** `frontend/components/connections/EmailConnectionFlow.tsx`, lines 56–63

```tsx
useEffect(() => {
  const params = new URLSearchParams(window.location.search)
  const connectedId = params.get('connected')
  if (connectedId) {
    setConnectionId(connectedId)
    setConnected(true)
  }
}, [])
```

On mount the component blindly trusts a `?connected=<id>` query parameter from the URL and immediately transitions to the post-OAuth "connected" state, setting `connectionId` to an arbitrary attacker-supplied value. This bypasses the OAuth flow entirely. An attacker can share a crafted URL such as:

```
/connections?connected=00000000-0000-0000-0000-000000000000
```

…and the victim's browser will be placed in the "Email Connected Successfully" UI, then allow the attacker to trigger `POST /api/v1/connections/email/<arbitrary-id>/scan` against a connection ID the victim does not own. The backend should enforce ownership, but the frontend is providing false confidence and could expose confusing UX or trigger unintended API calls against other users' connection IDs.

**Fix:** Validate the `connectedId` value before trusting it. At a minimum confirm it looks like a UUID (36-char format). Ideally pair it with a signed state token from the OAuth initiation step, or verify it against the authenticated user's existing connections before entering the "connected" state. Do not accept arbitrary URL-injected connection IDs without server-side confirmation.

---

### 2. `PortalConnectionFlow.tsx` — Plain-text password held in React state for entire session lifecycle

**File:** `frontend/components/connections/PortalConnectionFlow.tsx`, lines 37, 105

```tsx
const [portalPassword, setPortalPassword] = useState('')
// ...
portal_password: portalPassword,
```

The user's raw utility portal password is stored in React component state from the moment they type it until the component unmounts (success, error, or navigation away). Unlike `<input type="password">` which limits browser memory leaks, React state is retained in the JS heap and accessible via devtools or JS-based memory probes until garbage-collected. If the component is ever unmounted on "error" and re-mounted on "Try Again", the password re-populates from user re-entry, but between form open and success the password sits unobfuscated in memory.

More critically: the `portalLoginUrl` field accepts a `type="url"` input with no URL scheme allowlist. An attacker with XSS or a compromised backend response could influence the stored login URL.

**Fix:**
- Zero out `portalPassword` state immediately after the POST succeeds (before the component continues rendering) by calling `setPortalPassword('')`.
- Add explicit scheme validation to `portalLoginUrl` — accept only `https://` values, reject `http://`, `javascript:`, `data:`, and relative URLs.
- Consider adding a client-side warning if the login URL domain does not match a recognized utility domain from the suppliers registry.

---

## P1 — High

### 3. `BillUploadForm.tsx` — Polling interval leaks on rapid re-upload (stale interval reference)

**File:** `frontend/components/connections/BillUploadForm.tsx`, lines 100–147

`pollParseStatus` creates a new `setInterval` and assigns it to `pollIntervalRef.current`. `handleRetry` (line 244–249) calls `setParseResult(null)` and then immediately calls `handleUpload()`, which in turn calls `pollParseStatus()` again. However, between `handleRetry` calling `setParseResult(null)` and `handleUpload` completing the XHR upload, there is no guarantee the previous interval was cleared. The `clearFile` helper does clear the ref, but `handleRetry` calls `handleUpload` without first clearing the interval. If the prior upload completed and left the interval already cleared this is safe, but on a failed parse (status `'failed'`), the interval was cleared inside the polling loop — if that clear races with a fast retry, a second interval can be created before the first confirms it stopped.

More directly: if the user hits "Retry Upload" while the XHR is still in flight (network is slow), the `setParseResult(null)` call from `handleRetry` will not cancel the outstanding XHR, and the new `handleUpload` call will begin a second XHR. Two concurrent uploads for the same `connectionId` can result in two `pollParseStatus` intervals running simultaneously.

**Fix:** At the start of `handleRetry`, explicitly clear `pollIntervalRef.current` and abort any in-flight XHR. Use a `useRef<XMLHttpRequest>` to hold the active XHR, and abort it before re-triggering.

---

### 4. `ConnectionCard.tsx` — `connection.last_sync_error` rendered without sanitization

**File:** `frontend/components/connections/ConnectionCard.tsx`, line 381

```tsx
<p className="text-xs text-warning-700 truncate">
  {connection.last_sync_error}
</p>
```

`last_sync_error` is a server-supplied string. React's JSX rendering prevents HTML injection here (it escapes the content as text nodes), so this is **not** an HTML-injection risk in the current form. However, if this value ever gets passed to a `dangerouslySetInnerHTML` or a third-party rich-text renderer elsewhere, it would be a vector. The risk is low currently but worth annotating: this value should be treated as untrusted user-facing text and never rendered via `innerHTML`.

The more practical issue: there is no maximum length cap on what is displayed. A backend bug or an attacker-controlled error message could render a very long string. The `truncate` class limits visual overflow, but accessibility tools will read the full string.

**Fix:** Add a character cap (e.g., 200 chars) when displaying backend error strings: `{(connection.last_sync_error ?? '').slice(0, 200)}`. This is defensive and prevents screen-reader spam.

---

### 5. `PostForm.tsx` — No input ID on form labels, no `aria-invalid`, mutation error is not associated with the submit button

**File:** `frontend/components/community/PostForm.tsx`, lines 111–234

The `<label>` elements for "Post Type", "Utility Type", "Title", "Body", and rate fields use `className="block..."` but lack `htmlFor` attributes:

```tsx
<label className="block text-xs font-medium text-gray-600 mb-1">Post Type</label>
<select value={postType} ...>
```

None of the `<select>` or `<textarea>` inputs have `id` attributes, breaking the programmatic label-for-input association required by WCAG 1.3.1 (Info and Relationships) and 4.1.2. Screen readers will not announce the field label when focus enters the control.

Additionally, the error `<p>` elements use `data-testid` but lack `role="alert"` or `aria-live`, so screen reader users are not informed when validation errors appear without navigating to them.

**Fix:**
- Add `id="post-type-select"` (and matching `htmlFor`) to all labeled controls.
- Add `role="alert"` to all inline error paragraphs.
- Add `aria-describedby` to inputs that have associated error paragraphs.
- Add `aria-invalid={!!errors.field}` to fields with errors.

---

### 6. `VoteButton.tsx` — Optimistic revert uses stale `count` closure

**File:** `frontend/components/community/VoteButton.tsx`, lines 22–36

```tsx
const [optimisticCount, setOptimisticCount] = React.useState(count)

function handleClick() {
  const newVoted = !voted
  setVoted(newVoted)
  setOptimisticCount((c) => (newVoted ? c + 1 : Math.max(0, c - 1)))

  mutation.mutate(postId, {
    onError: () => {
      setVoted(!newVoted)
      setOptimisticCount(count)  // <-- stale closure over `count` prop
    },
  })
}
```

The `onError` callback reverts to `count` — the value of the prop at the time `handleClick` was called. If the parent re-renders with a new `count` (e.g. from a React Query refetch) between the click and the mutation error, the revert will set `optimisticCount` to the old prop value rather than the current server count. This is a subtle but real state drift that causes the displayed vote count to be incorrect after an error under concurrent activity.

**Fix:** Capture the current count at click time in a local variable: `const countAtClick = optimisticCount`, and revert to `countAtClick` in the error handler instead of the prop `count`.

---

### 7. `SavingsEstimateCard.tsx` — Negative "best available cost" renders without guard

**File:** `frontend/components/connections/analytics/SavingsEstimateCard.tsx`, lines 134–140

```tsx
<span className="font-semibold text-success-700">
  {formatCurrency(
    data.current_annual_cost - data.estimated_annual_savings_vs_best
  )}
</span>
```

If `estimated_annual_savings_vs_best` exceeds `current_annual_cost` (a plausible backend data anomaly), the subtraction yields a negative value. `Intl.NumberFormat` with `style: 'currency'` will render "-$0" or "-$50", presenting the user with a nonsensical "best available annual cost" of negative dollars. There is no guard checking this result is `>= 0` before rendering.

**Fix:** Clamp the result: `Math.max(0, data.current_annual_cost - data.estimated_annual_savings_vs_best)`.

---

### 8. `ConnectionAnalytics.tsx` — `handleSyncConnection` throws unhandled on error; children receive `onSync` that can reject silently

**File:** `frontend/components/connections/ConnectionAnalytics.tsx`, lines 42–55

```tsx
const handleSyncConnection = useCallback(async (connectionId: string) => {
  const res = await fetch(...)
  if (!res.ok) {
    throw new Error('Sync failed')
  }
  setRefreshKey((k) => k + 1)
}, [])
```

`handleSyncConnection` is passed as `onSync` to `ConnectionHealthCard`. In `ConnectionHealthCard.handleSyncConnection` (line 53–65 of `ConnectionHealthCard.tsx`), it awaits `onSync(connectionId)` inside a try/finally block — the thrown error is silently swallowed in the `finally` because there is no `catch`. The user sees the spinner disappear with no error message when a sync fails from the analytics panel.

**Fix:** Either wrap the throw into a user-visible error state within `ConnectionHealthCard.handleSyncConnection`, or pass a separate `onSyncError` callback. As a minimum add a `catch (err)` block in `ConnectionHealthCard.handleSyncConnection` and surface the error.

---

## P2 — Medium

### 9. `PortalConnectionFlow.tsx` — AbortController `timeout` is declared but never actually used by `createPortalConnection`

**File:** `frontend/components/connections/PortalConnectionFlow.tsx`, lines 96–110

```tsx
const controller = new AbortController()
const timeout = setTimeout(() => controller.abort(), 30_000)

try {
  setStep('submitting')
  const connection = await createPortalConnection({
    supplier_id: selectedSupplierId,
    portal_username: portalUsername.trim(),
    portal_password: portalPassword,
    portal_login_url: portalLoginUrl.trim() || undefined,
    consent_given: true,
  })
  clearTimeout(timeout)
```

`controller` is created and `timeout` calls `controller.abort()` after 30s, but `controller.signal` is **never passed** to `createPortalConnection`. The `createPortalConnection` call in `portal.ts` accepts an `options?: { signal?: AbortSignal }` parameter but receives nothing here, so the abort never reaches the fetch. The timeout fires after 30s, calls `controller.abort()` on an orphaned controller, and the in-flight HTTP request continues running until the server times out.

Similarly, `scrapeController` and `scrapeTimeout` (lines 114–115) create another controller whose signal is also never passed to `triggerPortalScrape`.

**Fix:** Pass the signal:
```tsx
const connection = await createPortalConnection(
  { supplier_id: selectedSupplierId, ... },
  { signal: controller.signal }
)
```
```tsx
const result = await triggerPortalScrape(
  connection.connection_id,
  { signal: scrapeController.signal }
)
```

---

### 10. `BillUploadForm.tsx` — `handleRetry` triggers upload without resetting `selectedFile` guard

**File:** `frontend/components/connections/BillUploadForm.tsx`, lines 244–249

```tsx
const handleRetry = () => {
  setParseResult(null)
  setUploadProgress(0)
  setError(null)
  handleUpload()
}
```

`handleRetry` is invoked from `BillUploadFailure` after a parse failure. At that point, the UI hides the drop zone (`!isProcessing && !isComplete` check on line 276). The `BillUploadDropZone` is hidden, but the `selectedFile` is still set. The retry works correctly. However, if `clearFile` is called between the failure display and a rapid retry (possible via keyboard shortcuts or test automation), `selectedFile` becomes `null` but `handleRetry` does not check — it calls `handleUpload` which then calls `setError('Please select a file first')`. The UX shows both the failure component and a new "Please select a file" error simultaneously, which is confusing.

**Fix:** Add `if (!selectedFile) { setError('Select a file before retrying'); return }` at the top of `handleRetry`, or disable the retry button when `selectedFile` is null.

---

### 11. `PostList.tsx` — Missing `aria-label` on pagination buttons; `timeAgo` returns "0m ago" for fresh posts

**File:** `frontend/components/community/PostList.tsx`, lines 82–98

The "Previous" and "Next" buttons have no `aria-label` distinguishing them from similarly-labelled buttons elsewhere on the page. WCAG 4.1.2 requires all controls to have accessible names that convey their purpose in context.

The `timeAgo` function (line 18–25) returns `"0m ago"` for posts created within the last minute, which is technically correct but looks like a rendering bug to users. Posts that are seconds old show "0m ago."

**Fix:**
- Add `aria-label="Go to previous page"` / `aria-label="Go to next page"` to pagination buttons.
- Add a `< 1` minute check returning `"just now"`.

---

### 12. `CCAAlert.tsx` — Region string slicing assumes `us_` prefix unconditionally

**File:** `frontend/components/cca/CCAAlert.tsx`, line 13

```tsx
const stateCode = region ? region.slice(3).toUpperCase() : undefined
```

The CLAUDE.md documents that the Region enum supports "50 states + DC + international". International regions do not follow the `us_XX` pattern. For example, `ca_on` (Ontario, Canada) sliced at `[3:]` gives `"ON"` which happens to work, but `eu_de` (Germany) gives `"DE"`, and `intl_` prefixes give different lengths. The `CommunitySolarContent.tsx` guards with `region.startsWith('us_')` before slicing, but `CCAAlert.tsx` does not. For non-US international regions the CCA detect call is invoked with a nonsensical state code.

**Fix:** Mirror the guard used in `CommunitySolarContent.tsx`:
```tsx
const stateCode = region?.startsWith('us_') ? region.slice(3).toUpperCase() : undefined
```
And only call `useCCADetect` when `stateCode` is defined.

---

### 13. `CommunitySolarContent.tsx` — External `enrollment_url` rendered without validation

**File:** `frontend/components/community-solar/CommunitySolarContent.tsx`, lines 199–211

```tsx
{program.enrollment_url && (
  <a
    href={program.enrollment_url}
    target="_blank"
    rel="noopener noreferrer"
    ...
  >
```

`enrollment_url` is server-supplied. While `rel="noopener noreferrer"` is present (good), the href is not validated against an allowlist or scheme check before rendering. If a malicious entry reached the database (e.g., via a compromised admin account or SQL injection), a `javascript:` URL would execute in the user's browser when clicked. The same applies to `CCAInfo.tsx` `program_url` and `opt_out_url` (lines 100–119).

**Fix:** Add a client-side scheme guard before rendering external links. A simple helper:
```tsx
function isSafeHref(url: string): boolean {
  try {
    const { protocol } = new URL(url)
    return protocol === 'https:' || protocol === 'http:'
  } catch { return false }
}
```
Then: `href={isSafeHref(program.enrollment_url) ? program.enrollment_url : '#'}`.

---

### 14. `DirectLoginForm.tsx` — No abort controller on supplier registry fetch; loads during every mount

**File:** `frontend/components/connections/DirectLoginForm.tsx`, lines 75–92

The `useEffect` that loads the supplier registry has no cleanup (no `AbortController`). If the component unmounts during the inflight request (e.g., user immediately navigates away), the `setSuppliers` / `setLoadingSuppliers` state updates will fire on the unmounted component, producing a React "setState on unmounted component" warning in development. In React 18 strict mode this warning has been removed from the console but the state leak remains.

**Fix:** Add an abort controller in the effect:
```tsx
useEffect(() => {
  const controller = new AbortController()
  async function load() {
    try {
      const res = await fetch(`${API_ORIGIN}/api/v1/suppliers/registry`, {
        credentials: 'include',
        signal: controller.signal,
      })
      ...
    } catch (err) {
      if ((err as DOMException).name === 'AbortError') return
      ...
    }
  }
  load()
  return () => controller.abort()
}, [])
```
The same pattern is missing in `PortalConnectionFlow.tsx` line 50–67.

---

### 15. `RateHistoryCard.tsx` — Table has no `scope` on header cells; change calculation comment is misleading

**File:** `frontend/components/connections/analytics/RateHistoryCard.tsx`, lines 82–86

```tsx
<th className="px-4 py-2 font-medium text-gray-500">Date</th>
<th className="px-4 py-2 font-medium text-gray-500">Rate</th>
<th className="px-4 py-2 font-medium text-gray-500">Supplier</th>
<th className="px-4 py-2 font-medium text-gray-500 text-right">Change</th>
```

None of the `<th>` cells have `scope="col"`, which is required for accessible data tables (WCAG 1.3.1). The `ConnectionRates.tsx` table on line 248–260 has `scope="col"` — the history table is inconsistent.

The comment on line 91–93 describes the sort order as ambiguous ("newest-first or oldest-first"), which is a sign the component's contract with the API is unclear. The change calculation compares `data[idx + 1]` (the next entry in the array) as "previous period" — if the API returns ascending order, this is backwards and the change direction arrows will be inverted.

**Fix:**
- Add `scope="col"` to all four `<th>` elements.
- Clarify the sort-order contract in `fetchAnalytics` or the API, and update the change calculation accordingly.

---

## P3 — Low

### 16. `BillUploadFilePreview.tsx` — File name displayed without length truncation fallback for non-truncating contexts

**File:** `frontend/components/connections/BillUploadFilePreview.tsx`, line 29

```tsx
<p className="text-sm font-medium text-gray-900">{file.name}</p>
```

The filename is not truncated in this `<p>` tag (only the parent container uses `min-w-0`). Very long file names (e.g., a 200-character PDF name) will overflow on narrow viewports. The sibling `<p>` for size/type has `&middot;` separator but no equivalent truncation class.

**Fix:** Add `truncate` or `break-all` class to the filename `<p>`.

---

### 17. `PostForm.tsx` — Default region fallback `'us_ct'` is a hardcoded constant exposed in component code

**File:** `frontend/components/community/PostForm.tsx`, line 90

```tsx
region: region || 'us_ct',
```

The fallback `'us_ct'` (Connecticut) is a hardcoded magic string. Any new user without a configured region will have their community post tagged to Connecticut by default. This can pollute community data with misattributed regional posts. The correct behavior is either to block submission when region is unset (show a warning) or use a generic/national fallback.

**Fix:** Either validate that `region` is non-null before allowing submission (add a form-level validation error: "Please set your region in Settings before posting"), or use a defined constant from the Region enum rather than a hardcoded string literal.

---

### 18. `ConnectionCard.tsx` — Two `Connection` interface definitions (local vs. `ConnectionsOverview`)

**File:** `frontend/components/connections/ConnectionCard.tsx` lines 25–36 and `frontend/components/connections/ConnectionsOverview.tsx` lines 27–37

Both files define a local `interface Connection` with the same shape. There is no shared type file for this. If the backend adds a field (e.g., `utility_type`), it must be added in two places. The `ConnectionCard` version adds `label?: string | null` which is absent from `ConnectionsOverview`'s definition, creating a potential mismatch when `ConnectionsOverview` maps the API response and passes it to `ConnectionCard`.

**Fix:** Extract a shared `Connection` type to `frontend/lib/types/connection.ts` (or `frontend/lib/api/connections.ts`) and import it in both components.

---

### 19. `SavingsCalculator.tsx` (`CommunitySolarService`) — Component name mismatch creates confusion

**File:** `frontend/components/community-solar/SavingsCalculator.tsx`, lines 7–10 (comment) and export

The file is named `SavingsCalculator.tsx` but the exported function is `CommunitySolarService`. The import in `CommunitySolarContent.tsx` imports `{ CommunitySolarService }` from `'./SavingsCalculator'`. This naming mismatch (component name, file name, and import path all differ in intent) adds cognitive overhead. The inline comment acknowledges the discrepancy but does not fix it.

**Fix:** Rename the export to `SavingsCalculator` to match the file, and update the import in `CommunitySolarContent.tsx`.

---

### 20. `BillUploadProgress.tsx` — `BillUploadProgressBar` renders when `uploadProgress === 100` and `!uploading`

**File:** `frontend/components/connections/BillUploadProgress.tsx`, lines 13–16

```tsx
if (!uploading && !(uploadProgress > 0 && uploadProgress < 100)) {
  return null
}
```

This renders the bar when `uploading === true` (during upload) OR when `0 < uploadProgress < 100` (regardless of uploading). At `uploadProgress === 100` and `uploading === false` (immediately after XHR completes, before polling begins), the bar is hidden. This is the correct behaviour. However, the condition is convoluted double-negation. A bug in a future edit could easily invert the logic.

**Fix:** Rewrite as a positive expression for clarity:
```tsx
if (!uploading && (uploadProgress === 0 || uploadProgress >= 100)) {
  return null
}
```

---

### 21. `CCAInfo.tsx` — `error` silently suppressed; component returns `null` on error

**File:** `frontend/components/cca/CCAInfo.tsx`, lines 27–28

```tsx
if (error || !data) return null
```

When the CCA info API fails, the component renders nothing without notifying the user. If `CCAInfo` is rendered in a context where the user expects to see program details (e.g., after clicking "View Details" in `CCAAlert`), a silent blank is confusing. This is consistent with the community stats approach, but the contexts differ: stats are supplementary; program detail is primary content for this view.

**Fix:** Return a minimal error state (e.g., "Unable to load program details") rather than `null` when the component is the primary content of a panel.

---

### 22. `PostForm.tsx` — `rate_per_unit` validated only loosely; no minimum/maximum range check

**File:** `frontend/components/community/PostForm.tsx`, lines 91

```tsx
rate_per_unit: postType === 'rate_report' && ratePerUnit ? parseFloat(ratePerUnit) : null,
```

For `rate_report` posts, the rate value is passed to the backend as `parseFloat(ratePerUnit)` without any front-end range validation. A user can submit `rate_per_unit: 999999` or `rate_per_unit: -5`, which — while the backend should validate — the frontend should guard as well for UX. The `<input type="number" step="0.0001">` has no `min` or `max` attributes set.

**Fix:** Add `min="0.0001"` and `max="99.9999"` to the rate input, and add a validation rule in `validate()`:
```tsx
if (postType === 'rate_report' && ratePerUnit) {
  const v = parseFloat(ratePerUnit)
  if (isNaN(v) || v <= 0 || v > 99.9999) {
    errs.ratePerUnit = 'Rate must be between 0.0001 and 99.9999'
  }
}
```

---

## Summary

P0: 2  P1: 6  P2: 7  P3: 7

### Priority action list

1. **(P0)** Fix `EmailConnectionFlow.tsx` `?connected=` query-param trust — validate against user's actual connections or require a signed nonce.
2. **(P0)** Zero-out `portalPassword` state immediately after POST in `PortalConnectionFlow.tsx`; add `https://` scheme guard on `portalLoginUrl`.
3. **(P1)** Wire `controller.signal` into `createPortalConnection` and `triggerPortalScrape` calls in `PortalConnectionFlow.tsx` — the current abort controllers are no-ops.
4. **(P1)** Add `catch` to `ConnectionHealthCard.handleSyncConnection` so sync errors surface to the user instead of silently disappearing.
5. **(P1)** Add `htmlFor` / `id` pairs and `role="alert"` to all `PostForm.tsx` labels and error paragraphs.
6. **(P1)** Fix `VoteButton.tsx` stale `count` closure in `onError` revert.
7. **(P2)** Guard `CCAAlert.tsx` region slice against non-`us_` prefixes.
8. **(P2)** Add URL scheme validation for all server-supplied `href` values rendered from community solar and CCA data.
9. **(P2)** Add `scope="col"` to `RateHistoryCard.tsx` table headers; clarify sort-order contract.
10. **(P3)** Extract shared `Connection` interface to remove duplication between `ConnectionCard.tsx` and `ConnectionsOverview.tsx`.
