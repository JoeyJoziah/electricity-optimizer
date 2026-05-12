import { renderHook, act } from "@testing-library/react";
import {
  useSettingsStore,
  useRegion,
  useUtilityTypes,
  useCurrentSupplier,
  usePriceAlerts,
} from "@/lib/store/settings";

beforeEach(() => {
  useSettingsStore.setState({
    region: undefined,
    utilityTypes: ["electricity"],
    currentSupplier: null,
    annualUsageKwh: 10500,
    peakDemandKw: 5,
    appliances: [],
    priceAlerts: [],
    notificationPreferences: {
      priceAlerts: true,
      optimalTimes: true,
      supplierUpdates: false,
    },
    displayPreferences: {
      currency: "USD",
      theme: "system",
      timeFormat: "12h",
    },
  });
});

describe("useSettingsStore — region", () => {
  it("starts with undefined region", () => {
    expect(useSettingsStore.getState().region).toBeUndefined();
  });

  it("setRegion updates region", () => {
    useSettingsStore.getState().setRegion("us_ct");
    expect(useSettingsStore.getState().region).toBe("us_ct");
  });
});

describe("useSettingsStore — utility types", () => {
  it("defaults to electricity", () => {
    expect(useSettingsStore.getState().utilityTypes).toEqual(["electricity"]);
  });

  it("setUtilityTypes replaces array", () => {
    useSettingsStore.getState().setUtilityTypes(["natural_gas", "propane"]);
    expect(useSettingsStore.getState().utilityTypes).toEqual([
      "natural_gas",
      "propane",
    ]);
  });
});

describe("useSettingsStore — appliances", () => {
  it("starts with empty appliances", () => {
    expect(useSettingsStore.getState().appliances).toEqual([]);
  });

  it("addAppliance appends to the list", () => {
    const appliance = {
      id: "app-1",
      name: "HVAC",
      type: "heating_cooling" as const,
      powerKw: 3.5,
      hoursPerDay: 8,
    };
    useSettingsStore.getState().addAppliance(appliance);
    expect(useSettingsStore.getState().appliances).toHaveLength(1);
    expect(useSettingsStore.getState().appliances[0].name).toBe("HVAC");
  });

  it("removeAppliance deletes by id", () => {
    const appliance = {
      id: "app-2",
      name: "Washer",
      type: "other" as const,
      powerKw: 1.2,
      hoursPerDay: 1,
    };
    useSettingsStore.getState().addAppliance(appliance);
    useSettingsStore.getState().removeAppliance("app-2");
    expect(useSettingsStore.getState().appliances).toHaveLength(0);
  });

  it("updateAppliance patches by id", () => {
    const appliance = {
      id: "app-3",
      name: "Dryer",
      type: "other" as const,
      powerKw: 2.0,
      hoursPerDay: 1,
    };
    useSettingsStore.getState().addAppliance(appliance);
    useSettingsStore.getState().updateAppliance("app-3", { hoursPerDay: 2 });
    expect(useSettingsStore.getState().appliances[0].hoursPerDay).toBe(2);
    expect(useSettingsStore.getState().appliances[0].name).toBe("Dryer");
  });
});

describe("useSettingsStore — price alerts", () => {
  it("addPriceAlert appends alert", () => {
    useSettingsStore.getState().addPriceAlert({
      id: "alert-1",
      type: "below",
      threshold: 0.1,
      enabled: true,
    });
    expect(useSettingsStore.getState().priceAlerts).toHaveLength(1);
  });

  it("removePriceAlert removes by id", () => {
    useSettingsStore.getState().addPriceAlert({
      id: "alert-2",
      type: "above",
      threshold: 0.2,
      enabled: true,
    });
    useSettingsStore.getState().removePriceAlert("alert-2");
    expect(useSettingsStore.getState().priceAlerts).toHaveLength(0);
  });

  it("togglePriceAlert flips enabled", () => {
    useSettingsStore.getState().addPriceAlert({
      id: "alert-3",
      type: "below",
      threshold: 0.15,
      enabled: true,
    });
    useSettingsStore.getState().togglePriceAlert("alert-3");
    expect(useSettingsStore.getState().priceAlerts[0].enabled).toBe(false);
    useSettingsStore.getState().togglePriceAlert("alert-3");
    expect(useSettingsStore.getState().priceAlerts[0].enabled).toBe(true);
  });
});

describe("useSettingsStore — preferences", () => {
  it("setNotificationPreferences merges partial update", () => {
    useSettingsStore.getState().setNotificationPreferences({
      supplierUpdates: true,
    });
    const prefs = useSettingsStore.getState().notificationPreferences;
    expect(prefs.supplierUpdates).toBe(true);
    expect(prefs.priceAlerts).toBe(true);
  });

  it("setDisplayPreferences merges partial update", () => {
    useSettingsStore.getState().setDisplayPreferences({ currency: "EUR" });
    expect(useSettingsStore.getState().displayPreferences.currency).toBe("EUR");
    expect(useSettingsStore.getState().displayPreferences.theme).toBe("system");
  });
});

describe("useSettingsStore — resetSettings", () => {
  it("resets to defaults", () => {
    useSettingsStore.getState().setRegion("us_tx");
    useSettingsStore.getState().setAnnualUsage(20000);
    useSettingsStore.getState().resetSettings();
    expect(useSettingsStore.getState().region).toBeUndefined();
    expect(useSettingsStore.getState().annualUsageKwh).toBe(10500);
  });
});

describe("selector hooks", () => {
  it("useRegion returns current region", () => {
    const { result } = renderHook(() => useRegion());
    act(() => {
      useSettingsStore.getState().setRegion("us_ma");
    });
    expect(result.current).toBe("us_ma");
  });

  it("useUtilityTypes returns current types", () => {
    const { result } = renderHook(() => useUtilityTypes());
    expect(result.current).toContain("electricity");
  });

  it("useCurrentSupplier returns null initially", () => {
    const { result } = renderHook(() => useCurrentSupplier());
    expect(result.current).toBeNull();
  });

  it("usePriceAlerts returns empty array initially", () => {
    const { result } = renderHook(() => usePriceAlerts());
    expect(result.current).toEqual([]);
  });
});
