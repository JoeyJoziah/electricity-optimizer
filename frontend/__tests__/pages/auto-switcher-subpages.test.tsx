// ---------------------------------------------------------------------------
// These pages are thin wrappers that delegate entirely to a content component
// that lives as a sibling file. We verify only the metadata export since the
// content components are already tested elsewhere (AutoSwitcherContent tests).
// ---------------------------------------------------------------------------

import { metadata as historyMetadata } from "@/app/(app)/auto-switcher/history/page";
import { metadata as settingsMetadata } from "@/app/(app)/auto-switcher/settings/page";

describe("SwitchHistoryPage metadata", () => {
  it("has correct title", () => {
    expect(historyMetadata.title).toBe("Switch History | RateShift");
  });
});

describe("AutoSwitcherSettingsPage metadata", () => {
  it("has correct title", () => {
    expect(settingsMetadata.title).toBe("Auto Switcher Settings | RateShift");
  });
});
