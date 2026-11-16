import { render, screen } from "@testing-library/react";

jest.mock("next/navigation", () => ({
  notFound: jest.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  }),
}));

jest.mock("@/components/seo/RatePageContent", () => ({
  RatePageContent: (props: {
    stateName: string;
    utilityLabel: string;
    rateData: unknown;
  }) => (
    <div data-testid="rate-content">
      {props.stateName}|{props.utilityLabel}|{props.rateData ? "data" : "empty"}
    </div>
  ),
}));

import RatePage, {
  generateMetadata,
  generateStaticParams,
} from "@/app/rates/[state]/[utility]/page";

const params = (state: string, utility: string) =>
  Promise.resolve({ state, utility });

describe("public rate page", () => {
  const realFetch = global.fetch;
  afterEach(() => {
    global.fetch = realFetch;
  });

  it("generates a page for every state and utility pair", async () => {
    const all = await generateStaticParams();
    expect(all).toContainEqual({
      state: "connecticut",
      utility: "electricity",
    });
    expect(new Set(all.map((p) => `${p.state}/${p.utility}`)).size).toBe(
      all.length,
    );
  });

  it("builds metadata for a valid pair", async () => {
    const meta = await generateMetadata({
      params: params("connecticut", "electricity"),
    });
    expect(meta.title).toBe("Electricity Rates in Connecticut — RateShift");
    expect(meta.alternates?.canonical).toMatch(
      /\/rates\/connecticut\/electricity$/,
    );
  });

  it("returns empty metadata for an unknown state or utility", async () => {
    expect(
      await generateMetadata({ params: params("atlantis", "electricity") }),
    ).toEqual({});
    expect(
      await generateMetadata({ params: params("connecticut", "plutonium") }),
    ).toEqual({});
  });

  it("renders with backend data", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ average_price: 0.25 }),
    }) as unknown as typeof fetch;

    render(await RatePage({ params: params("connecticut", "electricity") }));

    expect(screen.getByTestId("rate-content")).toHaveTextContent(
      "Connecticut|Electricity|data",
    );
    expect(
      document.querySelector('script[type="application/ld+json"]'),
    ).not.toBeNull();
  });

  it("renders the empty state when the backend answers non-OK", async () => {
    global.fetch = jest
      .fn()
      .mockResolvedValue({ ok: false }) as unknown as typeof fetch;

    render(await RatePage({ params: params("connecticut", "electricity") }));

    expect(screen.getByTestId("rate-content")).toHaveTextContent("empty");
  });

  it("renders the empty state when the backend is unreachable", async () => {
    global.fetch = jest
      .fn()
      .mockRejectedValue(new Error("ECONNREFUSED")) as unknown as typeof fetch;

    render(await RatePage({ params: params("connecticut", "electricity") }));

    expect(screen.getByTestId("rate-content")).toHaveTextContent("empty");
  });

  it("calls notFound for an unknown state or utility", async () => {
    await expect(
      RatePage({ params: params("atlantis", "electricity") }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
    await expect(
      RatePage({ params: params("connecticut", "plutonium") }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
  });
});
