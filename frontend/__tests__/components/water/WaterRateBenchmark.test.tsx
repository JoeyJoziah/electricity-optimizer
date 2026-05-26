import { render, screen } from "@testing-library/react";
import { WaterRateBenchmark } from "@/components/water/WaterRateBenchmark";
import "@testing-library/jest-dom";

const mockUseWaterBenchmark = jest.fn();
jest.mock("@/lib/hooks/useWater", () => ({
  useWaterBenchmark: (...args: unknown[]) => mockUseWaterBenchmark(...args),
}));

const MOCK_BENCHMARK = {
  state: "NY",
  municipalities: 2,
  usage_gallons: 5760,
  avg_monthly_cost: 45.5,
  min_monthly_cost: 38.0,
  max_monthly_cost: 53.0,
  rates: [
    { municipality: "Buffalo", monthly_cost: 38.0, base_charge: 12.0 },
    { municipality: "New York", monthly_cost: 53.0, base_charge: 15.5 },
  ],
};

describe("WaterRateBenchmark", () => {
  beforeEach(() => {
    mockUseWaterBenchmark.mockReset();
  });

  it("shows loading skeleton", () => {
    mockUseWaterBenchmark.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    });
    const { container } = render(<WaterRateBenchmark state="NY" />);
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("shows an explicit empty-state message on error (no silent fallback)", () => {
    // ADR-011: errors must surface to the user, not render an empty <div>.
    mockUseWaterBenchmark.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error("fail"),
    });
    render(<WaterRateBenchmark state="NY" />);
    expect(
      screen.getByText(/No water rate data is available for NY/i),
    ).toBeInTheDocument();
  });

  it("renders nothing only when data is absent without an error", () => {
    mockUseWaterBenchmark.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    });
    const { container } = render(<WaterRateBenchmark state="NY" />);
    expect(container.innerHTML).toBe("");
  });

  it("displays benchmark summary cards", () => {
    mockUseWaterBenchmark.mockReturnValue({
      data: MOCK_BENCHMARK,
      isLoading: false,
      error: null,
    });
    render(<WaterRateBenchmark state="NY" />);

    expect(screen.getByText("Water Rate Benchmark — NY")).toBeInTheDocument();
    expect(screen.getByText("$45.50")).toBeInTheDocument();
    expect(screen.getByText("$38.00")).toBeInTheDocument();
    expect(screen.getByText("$53.00")).toBeInTheDocument();
  });

  it("displays municipality breakdown", () => {
    mockUseWaterBenchmark.mockReturnValue({
      data: MOCK_BENCHMARK,
      isLoading: false,
      error: null,
    });
    render(<WaterRateBenchmark state="NY" />);

    expect(screen.getByText("New York")).toBeInTheDocument();
    expect(screen.getByText("Buffalo")).toBeInTheDocument();
    expect(screen.getByText("Municipality Comparison")).toBeInTheDocument();
  });

  it("shows usage info", () => {
    mockUseWaterBenchmark.mockReturnValue({
      data: MOCK_BENCHMARK,
      isLoading: false,
      error: null,
    });
    render(<WaterRateBenchmark state="NY" />);

    expect(screen.getByText(/5,760 gallons\/month/)).toBeInTheDocument();
    expect(screen.getByText(/2 municipalities/)).toBeInTheDocument();
  });
});
