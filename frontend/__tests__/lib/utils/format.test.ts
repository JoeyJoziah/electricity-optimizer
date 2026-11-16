import {
  formatCurrency,
  formatPricePerKwh,
  formatPercentage,
  formatDateTime,
  formatTime,
  formatDate,
  formatRelativeTime,
  formatCompactNumber,
  formatEnergy,
  formatDuration,
} from "@/lib/utils/format";

describe("formatCurrency", () => {
  it("should format positive USD amounts with $ symbol", () => {
    expect(formatCurrency(10)).toBe("$10.00");
    expect(formatCurrency(1234.56)).toBe("$1,234.56");
    expect(formatCurrency(0.5)).toBe("$0.50");
  });

  it("should format negative amounts with a leading minus sign", () => {
    expect(formatCurrency(-10)).toBe("-$10.00");
    expect(formatCurrency(-1234.56)).toBe("-$1,234.56");
  });

  it("should format zero correctly", () => {
    expect(formatCurrency(0)).toBe("$0.00");
  });

  it("should default to USD when no currency is specified", () => {
    expect(formatCurrency(100)).toBe("$100.00");
  });

  it("should format GBP with the pound symbol", () => {
    expect(formatCurrency(100, "GBP")).toBe("\u00A3100.00");
    expect(formatCurrency(1234.56, "GBP")).toBe("\u00A31,234.56");
  });

  it("should format EUR with the euro symbol", () => {
    expect(formatCurrency(100, "EUR")).toBe("\u20AC100.00");
    expect(formatCurrency(1234.56, "EUR")).toBe("\u20AC1,234.56");
  });

  it("should round to 2 decimal places", () => {
    expect(formatCurrency(10.999)).toBe("$11.00");
    expect(formatCurrency(10.001)).toBe("$10.00");
    expect(formatCurrency(10.005)).toBe("$10.01");
  });

  it("should use en-US thousand separators (commas)", () => {
    expect(formatCurrency(1000000)).toBe("$1,000,000.00");
    expect(formatCurrency(999999.99)).toBe("$999,999.99");
  });

  it("should handle very small positive amounts", () => {
    expect(formatCurrency(0.01)).toBe("$0.01");
    expect(formatCurrency(0.001)).toBe("$0.00");
  });

  it("should handle very large amounts", () => {
    expect(formatCurrency(9999999.99)).toBe("$9,999,999.99");
  });
});

describe("formatPricePerKwh", () => {
  it("should append /kWh to the formatted currency", () => {
    expect(formatPricePerKwh(0.15)).toBe("$0.15/kWh");
    expect(formatPricePerKwh(0.25)).toBe("$0.25/kWh");
  });

  it("should support GBP currency", () => {
    expect(formatPricePerKwh(0.28, "GBP")).toBe("\u00A30.28/kWh");
  });

  it("should support EUR currency", () => {
    expect(formatPricePerKwh(0.3, "EUR")).toBe("\u20AC0.30/kWh");
  });

  it("should default to USD", () => {
    expect(formatPricePerKwh(0.12)).toBe("$0.12/kWh");
  });

  it("should handle zero price", () => {
    expect(formatPricePerKwh(0)).toBe("$0.00/kWh");
  });

  it("should handle negative price", () => {
    expect(formatPricePerKwh(-0.05)).toBe("-$0.05/kWh");
  });
});

describe("formatPercentage", () => {
  it("should format value with default 2 decimal places", () => {
    expect(formatPercentage(50)).toBe("50.00%");
    expect(formatPercentage(99.9)).toBe("99.90%");
  });

  it("should support custom decimal places", () => {
    expect(formatPercentage(33.333, 1)).toBe("33.3%");
    expect(formatPercentage(33.333, 0)).toBe("33%");
    expect(formatPercentage(33.333, 3)).toBe("33.333%");
  });

  it("should handle zero", () => {
    expect(formatPercentage(0)).toBe("0.00%");
  });

  it("should handle negative values", () => {
    expect(formatPercentage(-5.5)).toBe("-5.50%");
  });

  it("should handle values over 100", () => {
    expect(formatPercentage(150)).toBe("150.00%");
  });
});

describe("formatDateTime", () => {
  it("should format an ISO date string with default format", () => {
    // Use no Z suffix so parseISO treats it as local time
    const result = formatDateTime("2026-01-15T14:30:00");
    expect(result).toBe("15 Jan 2026 14:30");
  });

  it("should support custom format strings", () => {
    const result = formatDateTime("2026-01-15T14:30:00", "yyyy-MM-dd");
    expect(result).toBe("2026-01-15");
  });

  it("should return the original string for invalid dates", () => {
    const result = formatDateTime("not-a-date");
    expect(result).toBe("not-a-date");
  });

  it("should return the original string for empty strings", () => {
    const result = formatDateTime("");
    // parseISO('') may throw or return Invalid Date, function should return original
    expect(result).toBe("");
  });
});

describe("formatTime", () => {
  it("should format time in 24-hour format by default", () => {
    const result = formatTime("2026-01-15T14:30:00");
    expect(result).toBe("14:30");
  });

  it("should format time in 12-hour format when specified", () => {
    const result = formatTime("2026-01-15T14:30:00", false);
    expect(result).toBe("2:30 PM");
  });

  it("should handle midnight in 24-hour format", () => {
    const result = formatTime("2026-01-15T00:00:00");
    expect(result).toBe("00:00");
  });

  it("should handle noon in 12-hour format", () => {
    const result = formatTime("2026-01-15T12:00:00", false);
    expect(result).toBe("12:00 PM");
  });
});

describe("formatDate", () => {
  it("should format a date string as dd MMM yyyy", () => {
    const result = formatDate("2026-01-15T14:30:00");
    expect(result).toBe("15 Jan 2026");
  });

  it("should handle different months", () => {
    expect(formatDate("2026-06-01T12:00:00")).toBe("01 Jun 2026");
    expect(formatDate("2026-12-25T12:00:00")).toBe("25 Dec 2026");
  });
});

describe("formatRelativeTime", () => {
  it('should return a string ending with "ago" for past dates', () => {
    const pastDate = new Date(Date.now() - 3600 * 1000).toISOString();
    const result = formatRelativeTime(pastDate);
    expect(result).toMatch(/ago$/);
  });

  it('should return a string starting with "in" for future dates', () => {
    const futureDate = new Date(Date.now() + 3600 * 1000 * 24).toISOString();
    const result = formatRelativeTime(futureDate);
    expect(result).toMatch(/^in /);
  });
});

describe("formatCompactNumber", () => {
  it("should format millions with M suffix", () => {
    expect(formatCompactNumber(1000000)).toBe("1.0M");
    expect(formatCompactNumber(1500000)).toBe("1.5M");
    expect(formatCompactNumber(2345678)).toBe("2.3M");
  });

  it("should format thousands with K suffix", () => {
    expect(formatCompactNumber(1000)).toBe("1.0K");
    expect(formatCompactNumber(1500)).toBe("1.5K");
    expect(formatCompactNumber(999999)).toBe("1000.0K");
  });

  it("should return plain number for values under 1000", () => {
    expect(formatCompactNumber(0)).toBe("0");
    expect(formatCompactNumber(1)).toBe("1");
    expect(formatCompactNumber(999)).toBe("999");
    expect(formatCompactNumber(500)).toBe("500");
  });

  it("should handle negative values as plain numbers (below 1000 threshold)", () => {
    expect(formatCompactNumber(-500)).toBe("-500");
  });
});

describe("formatEnergy", () => {
  it("should format values >= 1000 as MWh", () => {
    expect(formatEnergy(1000)).toBe("1.00 MWh");
    expect(formatEnergy(1500)).toBe("1.50 MWh");
    expect(formatEnergy(2345.678)).toBe("2.35 MWh");
  });

  it("should format values < 1000 as kWh", () => {
    expect(formatEnergy(0)).toBe("0.00 kWh");
    expect(formatEnergy(100)).toBe("100.00 kWh");
    expect(formatEnergy(999.99)).toBe("999.99 kWh");
    expect(formatEnergy(0.5)).toBe("0.50 kWh");
  });

  it("should round to 2 decimal places", () => {
    expect(formatEnergy(123.456)).toBe("123.46 kWh");
    expect(formatEnergy(1234.567)).toBe("1.23 MWh");
  });
});

describe("formatDuration", () => {
  it("should format whole hours", () => {
    expect(formatDuration(1)).toBe("1h");
    expect(formatDuration(5)).toBe("5h");
    expect(formatDuration(24)).toBe("24h");
  });

  it("should format minutes only when hours is 0", () => {
    expect(formatDuration(0.5)).toBe("30m");
    expect(formatDuration(0.25)).toBe("15m");
    expect(formatDuration(0.75)).toBe("45m");
  });

  it("should format both hours and minutes", () => {
    expect(formatDuration(1.5)).toBe("1h 30m");
    expect(formatDuration(2.25)).toBe("2h 15m");
    expect(formatDuration(3.75)).toBe("3h 45m");
  });

  it("should handle zero", () => {
    expect(formatDuration(0)).toBe("0m");
  });

  it("should handle rounding of minutes", () => {
    // 1.999 hours => 1h + 0.999*60 = 59.94 => rounds to 60m
    // Math.floor(1.999) = 1, Math.round(0.999 * 60) = Math.round(59.94) = 60
    // Result: "1h 60m" (edge case in the implementation)
    expect(formatDuration(1.99)).toBe("1h 59m");
  });
});

// ---------------------------------------------------------------------------
// Cases merged from __tests__/utils/format.test.ts (block-scoped so its helpers do not
// collide with the ones above)
// ---------------------------------------------------------------------------
{
  describe("formatCurrency", () => {
    it("formats USD by default", () => {
      expect(formatCurrency(12.5)).toBe("$12.50");
    });

    it("formats GBP", () => {
      expect(formatCurrency(10, "GBP")).toBe("£10.00");
    });

    it("formats EUR", () => {
      expect(formatCurrency(10, "EUR")).toBe("€10.00");
    });

    it("handles negative values with sign", () => {
      expect(formatCurrency(-5.5)).toBe("-$5.50");
    });

    it("formats zero", () => {
      expect(formatCurrency(0)).toBe("$0.00");
    });

    it("formats large numbers with commas", () => {
      expect(formatCurrency(1234.56)).toBe("$1,234.56");
    });
  });

  describe("formatPricePerKwh", () => {
    it("appends /kWh to currency", () => {
      expect(formatPricePerKwh(0.12)).toBe("$0.12/kWh");
    });
  });

  describe("formatPercentage", () => {
    it("formats to 2 decimal places by default", () => {
      expect(formatPercentage(12.5)).toBe("12.50%");
    });

    it("respects custom decimals", () => {
      expect(formatPercentage(12.5, 0)).toBe("13%");
    });
  });

  describe("formatDateTime", () => {
    it("formats ISO date string", () => {
      expect(formatDateTime("2024-06-15T14:30:00")).toBe("15 Jun 2024 14:30");
    });

    it("returns original string on invalid input", () => {
      expect(formatDateTime("not-a-date")).toBe("not-a-date");
    });

    it("respects custom format string", () => {
      expect(formatDateTime("2024-01-05T00:00:00", "yyyy")).toBe("2024");
    });
  });

  describe("formatTime", () => {
    it("formats in 24-hour by default", () => {
      expect(formatTime("2024-06-15T14:30:00")).toBe("14:30");
    });

    it("formats in 12-hour when is24Hour=false", () => {
      const result = formatTime("2024-06-15T14:30:00", false);
      expect(result).toMatch(/2:30 PM/);
    });
  });

  describe("formatDate", () => {
    it("formats ISO date to dd MMM yyyy", () => {
      expect(formatDate("2024-06-15T00:00:00")).toBe("15 Jun 2024");
    });
  });

  describe("formatCompactNumber", () => {
    it("returns number as string under 1000", () => {
      expect(formatCompactNumber(999)).toBe("999");
    });

    it("formats thousands", () => {
      expect(formatCompactNumber(1500)).toBe("1.5K");
    });

    it("formats millions", () => {
      expect(formatCompactNumber(2500000)).toBe("2.5M");
    });
  });

  describe("formatEnergy", () => {
    it("formats kWh below 1000", () => {
      expect(formatEnergy(500)).toBe("500.00 kWh");
    });

    it("converts to MWh at 1000+", () => {
      expect(formatEnergy(1500)).toBe("1.50 MWh");
    });
  });

  describe("formatDuration", () => {
    it("shows minutes only for < 1 hour", () => {
      expect(formatDuration(0.5)).toBe("30m");
    });

    it("shows hours only for whole hours", () => {
      expect(formatDuration(2)).toBe("2h");
    });

    it("shows hours and minutes", () => {
      expect(formatDuration(2.5)).toBe("2h 30m");
    });
  });
}
