import {
  US_STATES,
  UTILITY_TYPES,
  stateToSlug,
  slugToStateCode,
  slugToUtilityKey,
  allStateSlugs,
  allUtilitySlugs,
} from "@/lib/config/seo";

describe("seo config", () => {
  it("has 51 states including DC", () => {
    expect(Object.keys(US_STATES)).toHaveLength(51);
    expect(US_STATES["DC"]).toBe("District of Columbia");
  });

  it("has 5 utility types", () => {
    expect(Object.keys(UTILITY_TYPES)).toHaveLength(5);
    expect(UTILITY_TYPES["electricity"]!.slug).toBe("electricity");
    expect(UTILITY_TYPES["natural_gas"]!.slug).toBe("natural-gas");
    expect(UTILITY_TYPES["heating_oil"]!.slug).toBe("heating-oil");
    expect(UTILITY_TYPES["propane"]!.slug).toBe("propane");
    expect(UTILITY_TYPES["water"]!.slug).toBe("water");
  });

  it("converts state name to slug", () => {
    expect(stateToSlug("New York")).toBe("new-york");
    expect(stateToSlug("Texas")).toBe("texas");
    expect(stateToSlug("District of Columbia")).toBe("district-of-columbia");
  });

  it("converts slug to state code", () => {
    expect(slugToStateCode("new-york")).toBe("NY");
    expect(slugToStateCode("texas")).toBe("TX");
    expect(slugToStateCode("district-of-columbia")).toBe("DC");
  });

  it("returns null for unknown state slug", () => {
    expect(slugToStateCode("narnia")).toBeNull();
  });

  it("converts utility slug to key", () => {
    expect(slugToUtilityKey("electricity")).toBe("electricity");
    expect(slugToUtilityKey("natural-gas")).toBe("natural_gas");
    expect(slugToUtilityKey("heating-oil")).toBe("heating_oil");
  });

  it("returns null for unknown utility slug", () => {
    expect(slugToUtilityKey("steam")).toBeNull();
  });

  it("allStateSlugs returns 51 slugs", () => {
    expect(allStateSlugs()).toHaveLength(51);
    expect(allStateSlugs()).toContain("new-york");
    expect(allStateSlugs()).toContain("texas");
  });

  it("allUtilitySlugs returns 5 slugs", () => {
    expect(allUtilitySlugs()).toHaveLength(5);
    expect(allUtilitySlugs()).toContain("electricity");
    expect(allUtilitySlugs()).toContain("natural-gas");
    expect(allUtilitySlugs()).toContain("propane");
    expect(allUtilitySlugs()).toContain("water");
  });
});
