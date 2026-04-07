/**
 * GA4 Analytics Component Tests
 *
 * TDD: tests written before implementation.
 * Covers: script rendering, env var gating, sanitization.
 */

import React from "react";
import { render } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Mock next/script — Jest/jsdom cannot execute real Script tags
// ---------------------------------------------------------------------------

jest.mock("next/script", () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const MockScript = (props: any) => (
    <script data-testid="next-script" {...props} />
  );
  MockScript.displayName = "MockScript";
  return MockScript;
});

// ---------------------------------------------------------------------------
// Module factory helpers — reset env between tests
// ---------------------------------------------------------------------------

function renderGA4(measurementId: string | undefined) {
  // Re-import the module after mutating the env so Next.js inlining is
  // bypassed in tests (the module reads from @/lib/config/env which reads
  // process.env at module evaluation time — we must re-isolate).
  jest.resetModules();
  process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = measurementId ?? "";

  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { GA4Analytics } = require("@/lib/analytics/ga4");
  return render(<GA4Analytics />);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("GA4Analytics component", () => {
  const originalEnv = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;

  afterEach(() => {
    process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = originalEnv ?? "";
    jest.resetModules();
  });

  it("renders nothing when NEXT_PUBLIC_GA_MEASUREMENT_ID is not set", () => {
    const { container } = renderGA4(undefined);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when NEXT_PUBLIC_GA_MEASUREMENT_ID is an empty string", () => {
    const { container } = renderGA4("");
    expect(container).toBeEmptyDOMElement();
  });

  it("renders two Script tags when measurement ID is present", () => {
    const { getAllByTestId } = renderGA4("G-TESTID1234");
    // Expects loader script + inline config script
    const scripts = getAllByTestId("next-script");
    expect(scripts.length).toBe(2);
  });

  it("loader script points to gtag.js with the measurement ID", () => {
    const id = "G-TESTID1234";
    const { getAllByTestId } = renderGA4(id);
    const scripts = getAllByTestId("next-script");
    const loader = scripts.find((s) =>
      s.getAttribute("src")?.includes("gtag/js"),
    );
    expect(loader).toBeDefined();
    expect(loader?.getAttribute("src")).toBe(
      `https://www.googletagmanager.com/gtag/js?id=${id}`,
    );
  });

  it('both scripts use strategy="lazyOnload"', () => {
    const { getAllByTestId } = renderGA4("G-TESTID1234");
    const scripts = getAllByTestId("next-script");
    scripts.forEach((s) => {
      expect(s.getAttribute("strategy")).toBe("lazyOnload");
    });
  });

  it("strips non-alphanumeric characters from measurement ID to prevent XSS", () => {
    // Malicious ID with script injection attempt — should be sanitized to only
    // keep letters, digits, and the allowed hyphen.
    const { getAllByTestId } = renderGA4("G-VALID<script>alert(1)</script>");
    const scripts = getAllByTestId("next-script");
    const loader = scripts.find((s) =>
      s.getAttribute("src")?.includes("gtag/js"),
    );
    // The src must NOT contain raw angle brackets
    expect(loader?.getAttribute("src")).not.toContain("<");
    expect(loader?.getAttribute("src")).not.toContain(">");
  });

  it("renders nothing when sanitized ID is empty", () => {
    // ID consisting entirely of non-alphanumeric chars → sanitized to ''
    const { container } = renderGA4("!!!---###");
    expect(container).toBeEmptyDOMElement();
  });
});
