import {
  DEREGULATED_ELECTRICITY_STATES,
  US_REGIONS,
  ALL_STATES,
  STATE_LABELS,
  US_STATES,
  US_STATES_ABBR,
} from "@/lib/constants/regions";

describe("DEREGULATED_ELECTRICITY_STATES", () => {
  it("contains Connecticut", () => {
    expect(DEREGULATED_ELECTRICITY_STATES.has("CT")).toBe(true);
  });

  it("contains Texas", () => {
    expect(DEREGULATED_ELECTRICITY_STATES.has("TX")).toBe(true);
  });

  it("does not contain California (regulated)", () => {
    expect(DEREGULATED_ELECTRICITY_STATES.has("CA")).toBe(false);
  });
});

describe("US_REGIONS", () => {
  it("contains at least 4 region groups", () => {
    expect(US_REGIONS.length).toBeGreaterThanOrEqual(4);
  });

  it("has a Northeast group", () => {
    const northeast = US_REGIONS.find((g) => g.label === "Northeast");
    expect(northeast).toBeDefined();
  });

  it("each state has value, label, and abbr", () => {
    US_REGIONS.forEach((group) => {
      group.states.forEach((state) => {
        expect(state.value).toBeTruthy();
        expect(state.label).toBeTruthy();
        expect(state.abbr).toBeTruthy();
      });
    });
  });

  it("CT has value us_ct", () => {
    const ct = US_REGIONS.find((g) => g.label === "Northeast")?.states.find(
      (s) => s.abbr === "CT",
    );
    expect(ct?.value).toBe("us_ct");
  });
});

describe("ALL_STATES", () => {
  it("is a flat list including all groups", () => {
    const expectedCount = US_REGIONS.reduce(
      (sum, g) => sum + g.states.length,
      0,
    );
    expect(ALL_STATES.length).toBe(expectedCount);
  });
});

describe("STATE_LABELS", () => {
  it("maps us_ct to Connecticut", () => {
    expect(STATE_LABELS["us_ct"]).toBe("Connecticut");
  });
});

describe("US_STATES", () => {
  it("maps CT to Connecticut", () => {
    expect(US_STATES["CT"]).toBe("Connecticut");
  });

  it("does not include international entries", () => {
    expect(US_STATES["UK"]).toBeUndefined();
  });
});

describe("US_STATES_ABBR", () => {
  it("is sorted alphabetically", () => {
    const copy = [...US_STATES_ABBR];
    expect(US_STATES_ABBR).toEqual(copy.sort());
  });

  it("contains CT", () => {
    expect(US_STATES_ABBR).toContain("CT");
  });
});
