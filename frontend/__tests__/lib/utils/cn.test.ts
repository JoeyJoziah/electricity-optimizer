import { cn } from "@/lib/utils/cn";

describe("cn", () => {
  it("returns a single class unchanged", () => {
    expect(cn("foo")).toBe("foo");
  });

  it("joins multiple classes with a space", () => {
    expect(cn("foo", "bar")).toBe("foo bar");
  });

  it("filters out falsy values", () => {
    expect(cn("foo", undefined, false, null, "bar")).toBe("foo bar");
  });

  it("handles conditional classes via object syntax", () => {
    expect(cn({ active: true, disabled: false })).toBe("active");
  });

  it("deduplicates conflicting Tailwind classes (last wins)", () => {
    expect(cn("p-4", "p-8")).toBe("p-8");
  });

  it("merges responsive and base variants correctly", () => {
    const result = cn("text-sm", "md:text-base");
    expect(result).toContain("text-sm");
    expect(result).toContain("md:text-base");
  });

  it("returns empty string when all inputs are falsy", () => {
    expect(cn(undefined, false, null)).toBe("");
  });

  it("handles array inputs from clsx", () => {
    expect(cn(["foo", "bar"])).toBe("foo bar");
  });
});
