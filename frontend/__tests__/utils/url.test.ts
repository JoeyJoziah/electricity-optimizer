import {
  isSafeRedirect,
  isSafeHref,
  isSafeOAuthRedirect,
} from "@/lib/utils/url";

const { location } = window;

beforeAll(() => {
  // jsdom sets window.location.origin to "http://localhost"
});

describe("isSafeRedirect", () => {
  it("allows same-origin relative path", () => {
    expect(isSafeRedirect("/dashboard")).toBe(true);
  });

  it("allows same-origin absolute URL", () => {
    expect(isSafeRedirect("http://localhost/dashboard")).toBe(true);
  });

  it("rejects external origin", () => {
    expect(isSafeRedirect("https://evil.com/steal")).toBe(false);
  });

  it("rejects protocol-relative URL to external host", () => {
    expect(isSafeRedirect("//evil.com")).toBe(false);
  });

  it("rejects javascript: URL", () => {
    expect(isSafeRedirect("javascript:alert(1)")).toBe(false);
  });
});

describe("isSafeHref", () => {
  it("allows https URLs", () => {
    expect(isSafeHref("https://example.com/page")).toBe(true);
  });

  it("allows http URLs", () => {
    expect(isSafeHref("http://example.com/page")).toBe(true);
  });

  it("rejects javascript: scheme", () => {
    expect(isSafeHref("javascript:alert(1)")).toBe(false);
  });

  it("rejects data: scheme", () => {
    expect(isSafeHref("data:text/html,<h1>X</h1>")).toBe(false);
  });

  it("rejects relative URLs (not parseable as absolute URL)", () => {
    expect(isSafeHref("/relative/path")).toBe(false);
  });
});

describe("isSafeOAuthRedirect", () => {
  it("allows same-origin URL regardless of allowlist", () => {
    expect(isSafeOAuthRedirect("http://localhost/callback", [])).toBe(true);
  });

  it("allows whitelisted external https origin", () => {
    expect(
      isSafeOAuthRedirect("https://accounts.google.com/o/oauth2", [
        "https://accounts.google.com",
      ]),
    ).toBe(true);
  });

  it("rejects whitelisted external origin over http", () => {
    expect(
      isSafeOAuthRedirect("http://accounts.google.com/o/oauth2", [
        "http://accounts.google.com",
      ]),
    ).toBe(false);
  });

  it("rejects external origin not in allowlist", () => {
    expect(
      isSafeOAuthRedirect("https://evil.com/steal", [
        "https://accounts.google.com",
      ]),
    ).toBe(false);
  });
});
