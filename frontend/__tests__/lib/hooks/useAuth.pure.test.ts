jest.mock("@/lib/auth/client", () => ({
  authClient: {
    signIn: { email: jest.fn(), social: jest.fn() },
    signOut: jest.fn(),
    signUp: { email: jest.fn() },
    sendMagicLink: jest.fn(),
    getSession: jest.fn(),
    useSession: jest.fn(),
  },
}));
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
}));
jest.mock("@/lib/api/suppliers", () => ({ getUserSupplier: jest.fn() }));
jest.mock("@/lib/api/profile", () => ({
  getUserProfile: jest.fn(),
  updateUserProfile: jest.fn(),
}));
jest.mock("@/lib/store/settings", () => ({
  useSettingsStore: jest.fn(() => ({
    setRegion: jest.fn(),
    region: undefined,
  })),
}));
jest.mock("@/lib/config/env", () => ({ API_URL: "https://api.test.invalid" }));
jest.mock("@/lib/notifications/onesignal", () => ({
  loginOneSignal: jest.fn(),
  logoutOneSignal: jest.fn(),
}));

import { checkNeedsOnboarding, checkNeedsRegion } from "@/lib/hooks/useAuth";

describe("checkNeedsOnboarding", () => {
  it("returns true when onboarding_completed is false", () => {
    expect(checkNeedsOnboarding({ onboarding_completed: false })).toBe(true);
  });

  it("returns true when onboarding_completed is undefined", () => {
    expect(checkNeedsOnboarding({})).toBe(true);
  });

  it("returns false when onboarding_completed is true", () => {
    expect(checkNeedsOnboarding({ onboarding_completed: true })).toBe(false);
  });
});

describe("checkNeedsRegion", () => {
  it("returns true when region is undefined", () => {
    expect(checkNeedsRegion({})).toBe(true);
  });

  it("returns true when region is null", () => {
    expect(checkNeedsRegion({ region: null })).toBe(true);
  });

  it("returns true when region is empty string", () => {
    expect(checkNeedsRegion({ region: "" })).toBe(true);
  });

  it("returns false when region is a non-empty string", () => {
    expect(checkNeedsRegion({ region: "us_ct" })).toBe(false);
  });
});
