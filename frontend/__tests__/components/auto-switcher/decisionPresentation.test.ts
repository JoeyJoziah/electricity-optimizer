import {
  formatCurrency,
  formatRate,
  formatDate,
  formatRelativeTime,
  daysUntil,
  decisionBadge,
} from "@/components/auto-switcher/decisionPresentation";

describe("formatCurrency", () => {
  it("returns '--' for null", () => {
    expect(formatCurrency(null)).toBe("--");
  });

  it("returns '--' for undefined", () => {
    expect(formatCurrency(undefined)).toBe("--");
  });

  it("formats a dollar amount with 2 decimal places", () => {
    expect(formatCurrency(4.99)).toBe("$4.99");
  });

  it("formats zero as '$0.00'", () => {
    expect(formatCurrency(0)).toBe("$0.00");
  });

  it("formats large numbers with commas", () => {
    const result = formatCurrency(1234.5);
    expect(result).toBe("$1,234.50");
  });
});

describe("formatRate", () => {
  it("returns '--' for null", () => {
    expect(formatRate(null)).toBe("--");
  });

  it("returns '--' for undefined", () => {
    expect(formatRate(undefined)).toBe("--");
  });

  it("formats a rate with 4 decimal places and /kWh suffix", () => {
    expect(formatRate(0.1234)).toBe("$0.1234/kWh");
  });

  it("formats zero correctly", () => {
    expect(formatRate(0)).toBe("$0.0000/kWh");
  });
});

describe("formatDate", () => {
  it("returns '--' for null", () => {
    expect(formatDate(null)).toBe("--");
  });

  it("returns '--' for undefined", () => {
    expect(formatDate(undefined)).toBe("--");
  });

  it("returns '--' for empty string", () => {
    expect(formatDate("")).toBe("--");
  });

  it("returns a non-empty string for a valid ISO date", () => {
    const result = formatDate("2026-05-12T18:00:00Z");
    expect(result).not.toBe("--");
    expect(result.length).toBeGreaterThan(0);
  });
});

describe("formatRelativeTime", () => {
  it("returns '--' for null", () => {
    expect(formatRelativeTime(null)).toBe("--");
  });

  it("returns '--' for undefined", () => {
    expect(formatRelativeTime(undefined)).toBe("--");
  });

  it("returns 'Expired' for a past timestamp", () => {
    expect(formatRelativeTime("2020-01-01T00:00:00Z")).toBe("Expired");
  });

  it("returns minutes remaining for a near-future timestamp", () => {
    const soon = new Date(Date.now() + 15 * 60 * 1000).toISOString();
    const result = formatRelativeTime(soon);
    expect(result).toMatch(/m remaining/);
  });

  it("returns hours and minutes remaining for hours away", () => {
    const future = new Date(
      Date.now() + 3 * 60 * 60 * 1000 + 30 * 60 * 1000,
    ).toISOString();
    const result = formatRelativeTime(future);
    expect(result).toMatch(/3h 30m remaining/);
  });

  it("returns days remaining for more than 24 hours away", () => {
    const future = new Date(Date.now() + 50 * 60 * 60 * 1000).toISOString();
    const result = formatRelativeTime(future);
    expect(result).toMatch(/\dd \dh remaining/);
  });
});

describe("daysUntil", () => {
  it("returns null for null input", () => {
    expect(daysUntil(null)).toBeNull();
  });

  it("returns null for undefined input", () => {
    expect(daysUntil(undefined)).toBeNull();
  });

  it("returns 0 for a past timestamp", () => {
    expect(daysUntil("2020-01-01T00:00:00Z")).toBe(0);
  });

  it("returns a positive number for a future timestamp", () => {
    const future = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString();
    const result = daysUntil(future);
    expect(result).toBeGreaterThanOrEqual(2);
    expect(result).toBeLessThanOrEqual(4);
  });

  it("never returns a negative number", () => {
    const past = new Date(Date.now() - 1000).toISOString();
    expect(daysUntil(past)).toBe(0);
  });
});

describe("decisionBadge", () => {
  it("returns success variant for 'switch'", () => {
    const result = decisionBadge("switch");
    expect(result.label).toBe("Switched");
    expect(result.variant).toBe("success");
  });

  it("returns info variant for 'recommend'", () => {
    const result = decisionBadge("recommend");
    expect(result.label).toBe("Recommendation");
    expect(result.variant).toBe("info");
  });

  it("returns default variant for 'hold'", () => {
    const result = decisionBadge("hold");
    expect(result.label).toBe("Hold");
    expect(result.variant).toBe("default");
  });

  it("returns warning variant for 'monitor'", () => {
    const result = decisionBadge("monitor");
    expect(result.label).toBe("Monitoring");
    expect(result.variant).toBe("warning");
  });

  it("returns the raw decision string as label for unknown decisions", () => {
    const result = decisionBadge("unknown_action");
    expect(result.label).toBe("unknown_action");
    expect(result.variant).toBe("default");
  });
});
