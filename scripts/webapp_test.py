"""Comprehensive Playwright webapp test for Electricity Optimizer.

Tests the live production site for:
- Page load and rendering
- Navigation and routing
- Auth flow accessibility
- Key UI elements and interactions
- API proxy health
- Error handling
"""

import json
import sys
import time
from playwright.sync_api import sync_playwright

BASE_URL = "https://rateshift.app"
RESULTS = []


def record(name, status, detail=""):
    RESULTS.append({"test": name, "status": status, "detail": detail})
    icon = "PASS" if status == "pass" else "FAIL" if status == "fail" else "WARN"
    print(f"  [{icon}] {name}" + (f" — {detail}" if detail else ""))


def test_homepage(page):
    """Test landing page loads and has key elements."""
    try:
        page.goto(f"{BASE_URL}/", wait_until="networkidle", timeout=30000)
        title = page.title()
        record("Homepage loads", "pass", f"Title: {title}")

        # Check for key landing page elements
        body_text = page.inner_text("body")
        if "electricity" in body_text.lower() or "energy" in body_text.lower() or "optimize" in body_text.lower():
            record("Homepage has relevant content", "pass")
        else:
            record("Homepage has relevant content", "warn", "No electricity/energy keywords found")

        # Check for navigation links
        nav_links = page.locator("a, button").count()
        record("Homepage has interactive elements", "pass" if nav_links > 3 else "warn", f"{nav_links} links/buttons")

        # Screenshot for reference
        page.screenshot(path="/tmp/eo-homepage.png", full_page=True)
        record("Homepage screenshot captured", "pass", "/tmp/eo-homepage.png")
    except Exception as e:
        record("Homepage loads", "fail", str(e)[:200])


def test_auth_pages(page):
    """Test auth pages are accessible."""
    auth_routes = [
        ("/auth/login", "Login"),
        ("/auth/signup", "Signup"),
        ("/auth/forgot-password", "Forgot Password"),
    ]
    for route, name in auth_routes:
        try:
            resp = page.goto(f"{BASE_URL}{route}", wait_until="networkidle", timeout=20000)
            status = resp.status if resp else 0

            if status == 200:
                # Check for form elements
                inputs = page.locator("input").count()
                buttons = page.locator("button").count()
                if inputs > 0 and buttons > 0:
                    record(f"{name} page functional", "pass", f"{inputs} inputs, {buttons} buttons")
                else:
                    record(f"{name} page functional", "warn", f"Missing form elements: {inputs} inputs, {buttons} buttons")
            else:
                record(f"{name} page accessible", "fail", f"HTTP {status}")
        except Exception as e:
            record(f"{name} page accessible", "fail", str(e)[:200])


def test_protected_routes_redirect(page):
    """Test that protected routes redirect to login."""
    protected_routes = [
        "/dashboard",
        "/prices",
        "/suppliers",
        "/connections",
        "/optimize",
        "/alerts",
        "/settings",
    ]
    for route in protected_routes:
        try:
            resp = page.goto(f"{BASE_URL}{route}", wait_until="networkidle", timeout=15000)
            current_url = page.url

            # Should redirect to login or show auth gate
            if "/auth/login" in current_url or "/auth" in current_url:
                record(f"{route} redirects to auth", "pass")
            elif resp and resp.status == 200:
                # Might render with auth gate (client-side redirect)
                body = page.inner_text("body")
                if "sign in" in body.lower() or "log in" in body.lower() or "loading" in body.lower():
                    record(f"{route} shows auth gate", "pass")
                else:
                    record(f"{route} auth protection", "warn", "Page loads without apparent auth check")
            else:
                record(f"{route} auth protection", "fail", f"HTTP {resp.status if resp else 'no response'}")
        except Exception as e:
            record(f"{route} auth protection", "fail", str(e)[:200])


def test_static_pages(page):
    """Test static/marketing pages."""
    static_routes = [
        ("/pricing", "Pricing"),
        ("/privacy", "Privacy Policy"),
        ("/terms", "Terms of Service"),
    ]
    for route, name in static_routes:
        try:
            resp = page.goto(f"{BASE_URL}{route}", wait_until="networkidle", timeout=15000)
            status = resp.status if resp else 0
            if status == 200:
                body = page.inner_text("body")
                has_content = len(body.strip()) > 100
                record(f"{name} page", "pass" if has_content else "warn",
                       f"HTTP {status}, {'content present' if has_content else 'minimal content'}")
            else:
                record(f"{name} page", "fail", f"HTTP {status}")
        except Exception as e:
            record(f"{name} page", "fail", str(e)[:200])


def test_api_proxy(page):
    """Test API proxy endpoints through the frontend."""
    try:
        # /api/v1/prices/current requires ?region= param — 422 proves proxy forwards to backend
        resp = page.goto(f"{BASE_URL}/api/v1/prices/current", wait_until="networkidle", timeout=15000)
        status = resp.status if resp else 0
        if status in (200, 401, 403, 422):
            record("API proxy reachable", "pass", f"HTTP {status} (proxy forwarding works)")
        elif status == 404:
            record("API proxy reachable", "warn", "404 — proxy may not be forwarding to backend")
        else:
            record("API proxy reachable", "warn", f"HTTP {status}")
    except Exception as e:
        record("API proxy reachable", "fail", str(e)[:200])


def test_performance(page):
    """Test page load performance."""
    try:
        start = time.time()
        page.goto(f"{BASE_URL}/", wait_until="networkidle", timeout=30000)
        load_time = time.time() - start

        if load_time < 3:
            record("Homepage load time", "pass", f"{load_time:.1f}s")
        elif load_time < 6:
            record("Homepage load time", "warn", f"{load_time:.1f}s (slow)")
        else:
            record("Homepage load time", "fail", f"{load_time:.1f}s (very slow)")

        # Check for console errors
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.reload(wait_until="networkidle")
        time.sleep(2)

        if console_errors:
            record("Console errors on homepage", "warn", f"{len(console_errors)} errors: {'; '.join(console_errors[:3])}")
        else:
            record("No console errors on homepage", "pass")
    except Exception as e:
        record("Performance test", "fail", str(e)[:200])


def test_404_handling(page):
    """Test 404 page handling."""
    try:
        resp = page.goto(f"{BASE_URL}/nonexistent-page-xyz", wait_until="networkidle", timeout=15000)
        status = resp.status if resp else 0
        if status == 404:
            record("404 handling", "pass", "Returns proper 404")
        elif status == 200:
            body = page.inner_text("body")
            if "not found" in body.lower() or "404" in body:
                record("404 handling", "pass", "Client-side 404 page")
            else:
                record("404 handling", "warn", "No 404 page — redirects or shows content")
        else:
            record("404 handling", "warn", f"HTTP {status}")
    except Exception as e:
        record("404 handling", "fail", str(e)[:200])


def test_security_headers(page):
    """Test security headers using direct HTTP request (Playwright navigation may not expose all headers)."""
    import subprocess
    try:
        result = subprocess.run(
            ["curl", "-sI", f"{BASE_URL}/"],
            capture_output=True, text=True, timeout=15
        )
        raw_headers = result.stdout.lower()

        security_headers = {
            "x-frame-options": "Clickjacking protection",
            "x-content-type-options": "MIME sniffing protection",
            "strict-transport-security": "HSTS",
            "content-security-policy": "CSP",
        }

        for header, desc in security_headers.items():
            if header in raw_headers:
                # Extract header value
                for line in result.stdout.splitlines():
                    if line.lower().startswith(header):
                        value = line.split(":", 1)[1].strip() if ":" in line else ""
                        record(f"Security: {desc}", "pass", f"{header}: {value[:60]}")
                        break
            else:
                record(f"Security: {desc}", "warn", f"Missing {header}")
    except Exception as e:
        record("Security headers", "fail", str(e)[:200])


def main():
    print("=" * 60)
    print("Electricity Optimizer — Webapp Test Suite")
    print(f"Target: {BASE_URL}")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ElectricityOptimizer-Test/1.0"
        )
        page = context.new_page()

        print("\n--- Homepage ---")
        test_homepage(page)

        print("\n--- Auth Pages ---")
        test_auth_pages(page)

        print("\n--- Protected Routes ---")
        test_protected_routes_redirect(page)

        print("\n--- Static Pages ---")
        test_static_pages(page)

        print("\n--- API Proxy ---")
        test_api_proxy(page)

        print("\n--- Performance ---")
        test_performance(page)

        print("\n--- 404 Handling ---")
        test_404_handling(page)

        print("\n--- Security Headers ---")
        test_security_headers(page)

        browser.close()

    # Summary
    print("\n" + "=" * 60)
    passes = sum(1 for r in RESULTS if r["status"] == "pass")
    fails = sum(1 for r in RESULTS if r["status"] == "fail")
    warns = sum(1 for r in RESULTS if r["status"] == "warn")
    total = len(RESULTS)
    print(f"RESULTS: {passes} pass, {fails} fail, {warns} warn / {total} total")

    if fails > 0:
        print("\nFAILURES:")
        for r in RESULTS:
            if r["status"] == "fail":
                print(f"  - {r['test']}: {r['detail']}")

    if warns > 0:
        print("\nWARNINGS:")
        for r in RESULTS:
            if r["status"] == "warn":
                print(f"  - {r['test']}: {r['detail']}")

    # Write JSON results
    with open("/tmp/eo-webapp-results.json", "w") as f:
        json.dump(RESULTS, f, indent=2)
    print(f"\nFull results: /tmp/eo-webapp-results.json")

    return 1 if fails > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
