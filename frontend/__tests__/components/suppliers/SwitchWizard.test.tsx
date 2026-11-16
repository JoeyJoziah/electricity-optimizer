import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import "@testing-library/jest-dom";
import { SwitchWizard } from "@/components/suppliers/SwitchWizard";
import type { Supplier } from "@/types";
import { waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

jest.mock("@/lib/utils/cn", () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(" "),
}));
jest.mock("@/lib/utils/format", () => ({
  formatCurrency: (v: number) => `$${v.toFixed(2)}`,
  formatPercentage: (v: number) => `${v}%`,
}));
jest.mock("@/components/ui/button", () => ({
  Button: (
    props: React.ButtonHTMLAttributes<HTMLButtonElement> & {
      children: React.ReactNode;
      loading?: boolean;
    },
  ) => (
    <button disabled={props.disabled} onClick={props.onClick}>
      {props.children}
    </button>
  ),
}));
jest.mock("@/components/ui/card", () => ({
  Card: ({ children, ...rest }: React.HTMLAttributes<HTMLDivElement>) => (
    <div {...rest}>{children}</div>
  ),
  CardContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));
jest.mock("@/components/ui/badge", () => ({
  Badge: ({ children }: { children: React.ReactNode }) => (
    <span>{children}</span>
  ),
}));
jest.mock("lucide-react", () => ({
  ArrowRight: () => <svg />,
  ArrowLeft: () => <svg />,
  Check: () => <svg />,
  X: () => <svg />,
  AlertTriangle: () => <svg />,
  Shield: () => <svg />,
  FileText: () => <svg />,
  Leaf: () => <svg />,
  Loader2: () => <svg />,
  CheckCircle2: () => <svg />,
  Star: () => <svg />,
  Zap: () => <svg />,
}));

function makeSupplier(id: string): Supplier {
  return {
    id,
    name: `Supplier ${id}`,
    rating: 4.2,
    avgPricePerKwh: 0.12,
    estimatedAnnualCost: 900,
    greenEnergy: false,
    contractLengthMonths: 12,
    exitFee: 0,
    logo: null,
    availableRegions: ["CT"],
  } as unknown as Supplier;
}

const recommendation = {
  supplier: makeSupplier("new"),
  currentSupplier: makeSupplier("current"),
  estimatedSavings: 100,
  paybackMonths: 3,
  confidence: 0.85,
};

describe("SwitchWizard", () => {
  it("renders the wizard with aria role=region", () => {
    render(<SwitchWizard recommendation={recommendation} />);
    expect(
      screen.getByRole("region", { name: /supplier switching wizard/i }),
    ).toBeInTheDocument();
  });

  it("shows Step 1 of 4 initially", () => {
    render(<SwitchWizard recommendation={recommendation} />);
    expect(screen.getByText("Step 1 of 4")).toBeInTheDocument();
  });

  it("advances to step 2 when Next is clicked", () => {
    render(<SwitchWizard recommendation={recommendation} />);
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(screen.getByText("Step 2 of 4")).toBeInTheDocument();
  });

  it("goes back to step 1 when Back is clicked on step 2", () => {
    render(<SwitchWizard recommendation={recommendation} />);
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    fireEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(screen.getByText("Step 1 of 4")).toBeInTheDocument();
  });

  it("calls onCancel when Cancel is clicked", () => {
    const onCancel = jest.fn();
    render(
      <SwitchWizard recommendation={recommendation} onCancel={onCancel} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Cases merged from __tests__/components/SwitchWizard.test.tsx (block-scoped so its helpers do not
// collide with the ones above)
// ---------------------------------------------------------------------------
{
  const mockRecommendation = {
    supplier: {
      id: "2",
      name: "NextEra Energy",
      logo: "/logos/nextera.png",
      avgPricePerKwh: 0.22,
      standingCharge: 0.45,
      greenEnergy: true,
      rating: 4.3,
      estimatedAnnualCost: 1050,
      tariffType: "variable" as const,
    },
    currentSupplier: {
      id: "1",
      name: "United Illuminating (UI)",
      logo: "/logos/ui.png",
      avgPricePerKwh: 0.28,
      standingCharge: 0.55,
      greenEnergy: false,
      rating: 3.8,
      estimatedAnnualCost: 1350,
      tariffType: "fixed" as const,
      exitFee: 50,
    },
    estimatedSavings: 300,
    paybackMonths: 2,
    confidence: 0.85,
  };

  describe("SwitchWizard", () => {
    it("shows recommendation in step 1", () => {
      render(<SwitchWizard recommendation={mockRecommendation} />);

      expect(screen.getByText("NextEra Energy")).toBeInTheDocument();
      expect(screen.getByText(/300/)).toBeInTheDocument();
      expect(
        screen.getByRole("heading", { name: /review recommendation/i }),
      ).toBeInTheDocument();
    });

    it("displays savings summary on first step", () => {
      render(<SwitchWizard recommendation={mockRecommendation} />);

      expect(screen.getByText(/save/i)).toBeInTheDocument();
      expect(screen.getAllByText(/year/i).length).toBeGreaterThan(0);
    });

    it("progresses through 4 steps correctly", async () => {
      const user = userEvent.setup();
      render(<SwitchWizard recommendation={mockRecommendation} />);

      // Step 1: Review
      expect(
        screen.getByRole("heading", { name: /review recommendation/i }),
      ).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: /next/i }));

      // Step 2: GDPR Consent
      await waitFor(() => {
        expect(
          screen.getByRole("heading", { name: /data consent/i }),
        ).toBeInTheDocument();
      });

      // Check consent checkbox
      const consentCheckbox = screen.getByRole("checkbox", {
        name: /consent/i,
      });
      await user.click(consentCheckbox);
      await user.click(screen.getByRole("button", { name: /next/i }));

      // Step 3: Contract Review
      await waitFor(() => {
        expect(
          screen.getByRole("heading", { name: /contract terms/i }),
        ).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /next/i }));

      // Step 4: Confirm
      await waitFor(() => {
        expect(
          screen.getByRole("heading", { name: /confirm switch/i }),
        ).toBeInTheDocument();
      });
    });

    it("requires GDPR consent before proceeding from step 2", async () => {
      const user = userEvent.setup();
      render(<SwitchWizard recommendation={mockRecommendation} />);

      // Go to step 2
      await user.click(screen.getByRole("button", { name: /next/i }));

      await waitFor(() => {
        expect(
          screen.getByRole("heading", { name: /data consent/i }),
        ).toBeInTheDocument();
      });

      // Try to proceed without consent - button should be disabled
      const nextButton = screen.getByRole("button", { name: /next/i });
      expect(nextButton).toBeDisabled();

      // Enable after checking consent
      const consentCheckbox = screen.getByRole("checkbox", {
        name: /consent/i,
      });
      await user.click(consentCheckbox);
      expect(nextButton).not.toBeDisabled();
    });

    it("shows exit fees and contract details in step 3", async () => {
      const user = userEvent.setup();
      render(<SwitchWizard recommendation={mockRecommendation} />);

      // Navigate to step 3
      await user.click(screen.getByRole("button", { name: /next/i }));

      await waitFor(() => {
        const consentCheckbox = screen.getByRole("checkbox", {
          name: /consent/i,
        });
        user.click(consentCheckbox);
      });

      await user.click(screen.getByRole("button", { name: /next/i }));

      await waitFor(() => {
        expect(
          screen.getByRole("heading", { name: /contract terms/i }),
        ).toBeInTheDocument();
        expect(screen.getAllByText(/exit fee/i).length).toBeGreaterThan(0);
      });
    });

    it("calls onComplete when switch is confirmed", async () => {
      const onComplete = jest.fn();
      const user = userEvent.setup();

      render(
        <SwitchWizard
          recommendation={mockRecommendation}
          onComplete={onComplete}
        />,
      );

      // Step 1: Review
      await user.click(screen.getByRole("button", { name: /next/i }));

      // Step 2: Consent
      await waitFor(async () => {
        const consentCheckbox = screen.getByRole("checkbox", {
          name: /consent/i,
        });
        await user.click(consentCheckbox);
      });
      await user.click(screen.getByRole("button", { name: /next/i }));

      // Step 3: Contract
      await waitFor(() => {
        expect(
          screen.getByRole("heading", { name: /contract terms/i }),
        ).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /next/i }));

      // Step 4: Confirm
      await waitFor(() => {
        expect(
          screen.getByRole("heading", { name: /confirm switch/i }),
        ).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /confirm/i }));

      await waitFor(() => {
        expect(onComplete).toHaveBeenCalled();
      });
    });

    it("allows going back to previous steps", async () => {
      const user = userEvent.setup();
      render(<SwitchWizard recommendation={mockRecommendation} />);

      // Go forward to step 2
      await user.click(screen.getByRole("button", { name: /next/i }));

      await waitFor(() => {
        expect(
          screen.getByRole("heading", { name: /data consent/i }),
        ).toBeInTheDocument();
      });

      // Go back to step 1
      await user.click(screen.getByRole("button", { name: /back/i }));

      await waitFor(() => {
        expect(
          screen.getByRole("heading", { name: /review recommendation/i }),
        ).toBeInTheDocument();
      });
    });

    it("calls onCancel when cancel button is clicked", async () => {
      const onCancel = jest.fn();
      const user = userEvent.setup();

      render(
        <SwitchWizard
          recommendation={mockRecommendation}
          onCancel={onCancel}
        />,
      );

      await user.click(screen.getByRole("button", { name: /cancel/i }));

      expect(onCancel).toHaveBeenCalled();
    });

    it("shows step progress indicator", () => {
      render(<SwitchWizard recommendation={mockRecommendation} />);

      expect(screen.getByText(/step 1 of 4/i)).toBeInTheDocument();
    });

    it("displays confidence level for the recommendation", () => {
      render(<SwitchWizard recommendation={mockRecommendation} />);

      expect(screen.getByText(/85%/)).toBeInTheDocument();
    });

    it("shows comparison between current and new supplier", () => {
      render(<SwitchWizard recommendation={mockRecommendation} />);

      expect(screen.getByText("United Illuminating (UI)")).toBeInTheDocument();
      expect(screen.getByText("NextEra Energy")).toBeInTheDocument();
    });

    it("handles API errors gracefully", async () => {
      const onComplete = jest.fn().mockRejectedValue(new Error("API Error"));
      const user = userEvent.setup();

      render(
        <SwitchWizard
          recommendation={mockRecommendation}
          onComplete={onComplete}
        />,
      );

      // Navigate through all steps
      await user.click(screen.getByRole("button", { name: /next/i }));
      await waitFor(async () => {
        await user.click(screen.getByRole("checkbox", { name: /consent/i }));
      });
      await user.click(screen.getByRole("button", { name: /next/i }));
      await waitFor(() => {
        expect(
          screen.getByRole("heading", { name: /contract terms/i }),
        ).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /next/i }));
      await waitFor(() => {
        expect(
          screen.getByRole("heading", { name: /confirm switch/i }),
        ).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /confirm/i }));

      await waitFor(() => {
        expect(screen.getByText("API Error")).toBeInTheDocument();
      });
    });

    it("shows loading state during submission", async () => {
      const onComplete = jest.fn(
        () => new Promise<void>((resolve) => setTimeout(resolve, 1000)),
      );
      const user = userEvent.setup();

      render(
        <SwitchWizard
          recommendation={mockRecommendation}
          onComplete={onComplete}
        />,
      );

      // Navigate through all steps quickly
      await user.click(screen.getByRole("button", { name: /next/i }));
      await waitFor(async () => {
        await user.click(screen.getByRole("checkbox", { name: /consent/i }));
      });
      await user.click(screen.getByRole("button", { name: /next/i }));
      await waitFor(() => {
        expect(
          screen.getByRole("heading", { name: /contract terms/i }),
        ).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /next/i }));
      await waitFor(() => {
        expect(
          screen.getByRole("heading", { name: /confirm switch/i }),
        ).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /confirm/i }));

      // Should show loading state
      expect(screen.getByText(/processing/i)).toBeInTheDocument();
    });

    it("is accessible with proper ARIA labels", () => {
      render(<SwitchWizard recommendation={mockRecommendation} />);

      // Wizard should be a dialog or region
      expect(
        screen.getByRole("region", { name: /supplier switching wizard/i }),
      ).toBeInTheDocument();
    });
  });
}
