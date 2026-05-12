import {
  generateStaticParams,
  generateMetadata,
} from "@/app/rates/[state]/[utility]/page";

jest.mock("@/components/seo/RatePageContent", () => ({
  RatePageContent: () => null,
}));

describe("rates/[state]/[utility] generateStaticParams", () => {
  it("returns an array", async () => {
    const params = await generateStaticParams();
    expect(Array.isArray(params)).toBe(true);
  });

  it("includes at least one entry per state × utility combination", async () => {
    const params = await generateStaticParams();
    // 51 states × 5 utility types = 255 entries minimum
    expect(params.length).toBeGreaterThanOrEqual(255);
  });

  it("each entry has state and utility keys", async () => {
    const params = await generateStaticParams();
    for (const p of params.slice(0, 10)) {
      expect(typeof p.state).toBe("string");
      expect(typeof p.utility).toBe("string");
    }
  });

  it("contains a Connecticut electricity entry", async () => {
    const params = await generateStaticParams();
    const ct = params.find(
      (p) => p.state === "connecticut" && p.utility === "electricity",
    );
    expect(ct).toBeDefined();
  });
});

describe("rates/[state]/[utility] generateMetadata", () => {
  it("returns empty object for unknown state slug", async () => {
    const meta = await generateMetadata({
      params: Promise.resolve({ state: "not-a-state", utility: "electricity" }),
    });
    expect(meta).toEqual({});
  });

  it("returns empty object for unknown utility slug", async () => {
    const meta = await generateMetadata({
      params: Promise.resolve({
        state: "connecticut",
        utility: "unknown-fuel",
      }),
    });
    expect(meta).toEqual({});
  });

  it("returns title for valid state + utility", async () => {
    const meta = await generateMetadata({
      params: Promise.resolve({ state: "connecticut", utility: "electricity" }),
    });
    expect(typeof meta.title).toBe("string");
    expect(String(meta.title)).toMatch(/Connecticut/);
    expect(String(meta.title)).toMatch(/Electricity/);
  });

  it("includes openGraph url", async () => {
    const meta = await generateMetadata({
      params: Promise.resolve({ state: "connecticut", utility: "electricity" }),
    });
    expect((meta.openGraph as { url?: string })?.url).toContain(
      "/rates/connecticut/electricity",
    );
  });

  it("includes canonical link", async () => {
    const meta = await generateMetadata({
      params: Promise.resolve({ state: "connecticut", utility: "electricity" }),
    });
    expect(meta.alternates?.canonical).toContain(
      "/rates/connecticut/electricity",
    );
  });
});
