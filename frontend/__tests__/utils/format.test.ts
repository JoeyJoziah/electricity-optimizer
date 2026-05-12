import {
  formatCurrency,
  formatPricePerKwh,
  formatPercentage,
  formatDateTime,
  formatTime,
  formatDate,
  formatCompactNumber,
  formatEnergy,
  formatDuration,
} from "@/lib/utils/format";

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
