import { isSafeRedirect, isSafeHref, isSafeOAuthRedirect } from "../url";

// jsdom sets window.location.origin to "http://localhost"
const CURRENT_ORIGIN = "http://localhost";

describe("isSafeRedirect", () => {
  it("allows relative paths (same origin)", () => {
    expect(isSafeRedirect("/dashboard")).toBe(true);
  });

  it("allows absolute same-origin URL", () => {
    expect(isSafeRedirect(`${CURRENT_ORIGIN}/settings`)).toBe(true);
  });

  it("rejects an external https URL", () => {
    expect(isSafeRedirect("https://evil.com/phish")).toBe(false);
  });

  it("rejects a javascript: URL", () => {
    expect(isSafeRedirect("javascript:alert(1)")).toBe(false);
  });

  it("rejects a protocol-relative URL pointing to an external host", () => {
    // '//evil.com/path' resolves with the current page's protocol
    // but origin becomes evil.com — must be rejected
    expect(isSafeRedirect("//evil.com/path")).toBe(false);
  });

  it("rejects a data: URL", () => {
    expect(isSafeRedirect("data:text/html,<script>alert(1)</script>")).toBe(
      false,
    );
  });

  it("allows root path '/'", () => {
    expect(isSafeRedirect("/")).toBe(true);
  });
});

describe("isSafeHref", () => {
  it("allows https URLs", () => {
    expect(isSafeHref("https://example.com/page")).toBe(true);
  });

  it("allows http URLs", () => {
    expect(isSafeHref("http://example.com/page")).toBe(true);
  });

  it("rejects javascript: URLs", () => {
    expect(isSafeHref("javascript:void(0)")).toBe(false);
  });

  it("rejects data: URLs", () => {
    expect(isSafeHref("data:text/html,<b>hi</b>")).toBe(false);
  });

  it("rejects vbscript: URLs", () => {
    expect(isSafeHref("vbscript:msgbox(1)")).toBe(false);
  });

  it("rejects protocol-relative URLs (no scheme)", () => {
    // new URL("//evil.com") throws → returns false
    expect(isSafeHref("//evil.com")).toBe(false);
  });

  it("rejects bare relative paths (no scheme)", () => {
    expect(isSafeHref("/relative/path")).toBe(false);
  });
});

describe("isSafeOAuthRedirect", () => {
  const allowed = [
    "https://accounts.google.com",
    "https://login.microsoftonline.com",
  ];

  it("allows same-origin URLs", () => {
    expect(
      isSafeOAuthRedirect(`${CURRENT_ORIGIN}/oauth/callback`, allowed),
    ).toBe(true);
  });

  it("rejects relative paths (no base URL parsing — throws → false)", () => {
    // isSafeOAuthRedirect uses new URL(url) without a base; relative paths throw
    expect(isSafeOAuthRedirect("/oauth/callback", allowed)).toBe(false);
  });

  it("allows whitelisted external https origin", () => {
    expect(
      isSafeOAuthRedirect("https://accounts.google.com/auth", allowed),
    ).toBe(true);
  });

  it("rejects non-whitelisted external https origin", () => {
    expect(isSafeOAuthRedirect("https://evil.com/steal", allowed)).toBe(false);
  });

  it("rejects http external origins even if host is whitelisted", () => {
    expect(
      isSafeOAuthRedirect("http://accounts.google.com/auth", allowed),
    ).toBe(false);
  });

  it("rejects javascript: URLs", () => {
    expect(isSafeOAuthRedirect("javascript:alert(1)", allowed)).toBe(false);
  });

  it("rejects external origin with empty allow list", () => {
    expect(isSafeOAuthRedirect("https://accounts.google.com/auth", [])).toBe(
      false,
    );
  });
});
