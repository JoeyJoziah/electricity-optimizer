"use client";

import React, { useState, useCallback, useEffect, useRef } from "react";
import Link from "next/link";
import { Header } from "@/components/layout/Header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ComparisonTable } from "@/components/suppliers/ComparisonTable";
import { SupplierCard } from "@/components/suppliers/SupplierCard";
import { SwitchWizard } from "@/components/suppliers/SwitchWizard";
import { SetSupplierDialog } from "@/components/suppliers/SetSupplierDialog";
import {
  useSuppliers,
  useSupplierRecommendation,
  useInitiateSwitch,
  useSetSupplier,
} from "@/lib/hooks/useSuppliers";
import { useSettingsStore } from "@/lib/store/settings";
import { formatCurrency } from "@/lib/utils/format";
import {
  Grid,
  List,
  TrendingDown,
  Award,
  Leaf,
  ArrowRight,
  Zap,
  Link2,
} from "lucide-react";
import type {
  Supplier,
  SupplierRecommendation,
  RawSupplierRecord,
} from "@/types";

type ViewMode = "grid" | "table";

/**
 * Generic focus-trap wrapper for inline dialogs.
 * Traps Tab cycling, handles Escape to close, prevents background scroll,
 * and restores focus on unmount.
 */
function FocusTrapOverlay({
  onClose,
  ariaLabel,
  children,
  maxWidth = "max-w-2xl",
}: {
  onClose: () => void;
  ariaLabel: string;
  children: React.ReactNode;
  maxWidth?: string;
}) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previouslyFocusedRef.current = document.activeElement as HTMLElement;

    // Prevent background scroll
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    // Focus first focusable element inside the dialog
    const timer = setTimeout(() => {
      const focusable = overlayRef.current?.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (focusable?.length) {
        focusable[0].focus();
      }
    }, 0);

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }

      if (e.key === "Tab") {
        const elements = overlayRef.current?.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (!elements?.length) return;

        const first = elements[0];
        const last = elements[elements.length - 1];

        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);

    return () => {
      clearTimeout(timer);
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = prevOverflow;
      previouslyFocusedRef.current?.focus();
    };
  }, [onClose]);

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-label={ariaLabel}
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
    >
      <div
        className={`max-h-[90vh] w-full ${maxWidth} overflow-y-auto rounded-xl bg-white p-6`}
      >
        {children}
      </div>
    </div>
  );
}

export default function SuppliersContent() {
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [selectedSupplier, setSelectedSupplier] = useState<Supplier | null>(
    null,
  );
  const [showWizard, setShowWizard] = useState(false);
  const [showSetDialog, setShowSetDialog] = useState(false);

  const region = useSettingsStore((s) => s.region);
  const annualUsage = useSettingsStore((s) => s.annualUsageKwh);
  const currentSupplier = useSettingsStore((s) => s.currentSupplier);
  const setCurrentSupplierStore = useSettingsStore((s) => s.setCurrentSupplier);

  // Fetch data
  const { data: suppliersData, isLoading: suppliersLoading } = useSuppliers(
    region,
    annualUsage,
  );
  const { data: recommendationData } = useSupplierRecommendation(
    currentSupplier?.id || "",
    annualUsage,
    region,
  );

  const initiateSwitch = useInitiateSwitch();
  const setSupplierMutation = useSetSupplier();

  // Map backend supplier fields to frontend Supplier type
  const suppliers: Supplier[] = (suppliersData?.suppliers || []).map(
    (s: RawSupplierRecord) => ({
      id: s.id,
      name: s.name,
      logo: s.logo || s.logo_url,
      avgPricePerKwh: s.avgPricePerKwh ?? s.avg_price_per_kwh ?? 0,
      standingCharge: s.standingCharge ?? s.standing_charge ?? 0,
      greenEnergy: s.greenEnergy ?? s.green_energy_provider ?? false,
      rating: s.rating ?? 0,
      estimatedAnnualCost:
        s.estimatedAnnualCost ?? s.estimated_annual_cost ?? 0,
      tariffType: (s.tariffType ??
        (s.tariff_types?.[0] || "variable")) as Supplier["tariffType"],
      exitFee: s.exitFee ?? s.exit_fee,
      contractLength: s.contractLength ?? s.contract_length,
      features: s.features ?? s.tariff_types,
    }),
  );
  const recommendation = recommendationData?.recommendation;

  // Handle supplier selection
  const handleSelectSupplier = useCallback(
    (supplier: Supplier) => {
      setSelectedSupplier(supplier);

      if (!currentSupplier) {
        // No current supplier — show simplified set dialog
        setShowSetDialog(true);
      } else {
        // Has current supplier — show full switch wizard
        setShowWizard(true);
      }
    },
    [currentSupplier],
  );

  // Handle first-time supplier set (from SetSupplierDialog)
  const handleSetSupplier = useCallback(
    async (supplier: Supplier) => {
      try {
        await setSupplierMutation.mutateAsync(supplier.id);
      } catch {
        // Backend save failed — still update local state for offline-first UX
      }
      setCurrentSupplierStore(supplier);
      setShowSetDialog(false);
      setSelectedSupplier(null);
    },
    [setSupplierMutation, setCurrentSupplierStore],
  );

  // Handle switch completion (from SwitchWizard)
  const handleSwitchComplete = useCallback(async () => {
    if (!selectedSupplier) return;

    try {
      await setSupplierMutation.mutateAsync(selectedSupplier.id);
    } catch {
      // Backend save failed — still update local state
    }

    try {
      await initiateSwitch.mutateAsync({
        newSupplierId: selectedSupplier.id,
        gdprConsent: true,
        currentSupplierId: currentSupplier?.id,
      });
    } catch {
      // Switch endpoint may not exist yet — that's OK, supplier was already set
    }

    setCurrentSupplierStore(selectedSupplier);
    setShowWizard(false);
    setSelectedSupplier(null);
  }, [
    selectedSupplier,
    setSupplierMutation,
    initiateSwitch,
    currentSupplier,
    setCurrentSupplierStore,
  ]);

  // Close helpers
  const closeWizard = useCallback(() => {
    setShowWizard(false);
    setSelectedSupplier(null);
  }, []);

  const closeSetDialog = useCallback(() => {
    setShowSetDialog(false);
    setSelectedSupplier(null);
  }, []);

  // Find cheapest and greenest suppliers
  const cheapestSupplier = suppliers.length
    ? suppliers.reduce((min, s) =>
        s.estimatedAnnualCost < min.estimatedAnnualCost ? s : min,
      )
    : null;

  const greenestSupplier = suppliers
    .filter((s) => s.greenEnergy)
    .sort((a, b) => a.estimatedAnnualCost - b.estimatedAnnualCost)[0];

  // Wizard recommendation (only when switching from an existing supplier)
  const wizardRecommendation: SupplierRecommendation | null =
    selectedSupplier && currentSupplier
      ? {
          supplier: selectedSupplier,
          currentSupplier,
          estimatedSavings:
            currentSupplier.estimatedAnnualCost -
            selectedSupplier.estimatedAnnualCost,
          paybackMonths: currentSupplier.exitFee
            ? Math.ceil(
                currentSupplier.exitFee /
                  ((currentSupplier.estimatedAnnualCost -
                    selectedSupplier.estimatedAnnualCost) /
                    12),
              )
            : 0,
          confidence: 0.85,
        }
      : null;

  return (
    <div className="flex flex-col">
      <Header title="Compare Suppliers" />

      <div className="p-6">
        {/* Recommendation banner */}
        {recommendation && currentSupplier && (
          <Card className="mb-6 border-success-200 bg-success-50">
            <CardContent className="p-4">
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div className="flex items-center gap-4">
                  <Award
                    className="h-10 w-10 text-success-600"
                    aria-hidden="true"
                  />
                  <div>
                    <p className="font-semibold text-gray-900">
                      We found you a better deal!
                    </p>
                    <p className="text-success-700">
                      Switch to {recommendation.supplier.name} and save{" "}
                      <span className="font-bold">
                        {formatCurrency(recommendation.estimatedSavings)}
                      </span>{" "}
                      per year
                    </p>
                  </div>
                </div>
                <Button
                  variant="primary"
                  onClick={() => handleSelectSupplier(recommendation.supplier)}
                >
                  Switch Now
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Stats row */}
        <div className="mb-6 grid gap-4 md:grid-cols-3">
          {/* Cheapest */}
          <Card>
            <CardContent className="flex items-center gap-4 p-4">
              <div className="rounded-full bg-success-100 p-3">
                <TrendingDown
                  className="h-6 w-6 text-success-600"
                  aria-hidden="true"
                />
              </div>
              <div>
                <p className="text-sm text-gray-500">Cheapest Option</p>
                <p className="font-semibold text-gray-900">
                  {cheapestSupplier?.name || "--"}
                </p>
                <p className="text-success-600">
                  {cheapestSupplier
                    ? formatCurrency(cheapestSupplier.estimatedAnnualCost)
                    : "--"}
                  /year
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Greenest */}
          <Card>
            <CardContent className="flex items-center gap-4 p-4">
              <div className="rounded-full bg-success-100 p-3">
                <Leaf className="h-6 w-6 text-success-600" aria-hidden="true" />
              </div>
              <div>
                <p className="text-sm text-gray-500">Greenest Option</p>
                <p className="font-semibold text-gray-900">
                  {greenestSupplier?.name || "--"}
                </p>
                <p className="text-gray-600">100% Renewable</p>
              </div>
            </CardContent>
          </Card>

          {/* Your Current */}
          <Card>
            <CardContent className="flex items-center gap-4 p-4">
              <div className="rounded-full bg-primary-100 p-3">
                <Award
                  className="h-6 w-6 text-primary-600"
                  aria-hidden="true"
                />
              </div>
              <div>
                <p className="text-sm text-gray-500">Your Current</p>
                {currentSupplier ? (
                  <>
                    <p className="font-semibold text-gray-900">
                      {currentSupplier.name}
                    </p>
                    <p className="text-gray-600">
                      {formatCurrency(currentSupplier.estimatedAnnualCost)}/year
                    </p>
                  </>
                ) : (
                  <>
                    <p className="font-semibold text-gray-900">Not set</p>
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-1"
                      onClick={() => setShowSetDialog(true)}
                    >
                      <Zap className="mr-1 h-3 w-3" />
                      Select Supplier
                    </Button>
                  </>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* View toggle and filters */}
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">
            {suppliers.length} Suppliers Available
          </h2>
          <div
            className="flex items-center gap-2"
            role="group"
            aria-label="View mode"
          >
            <Button
              variant={viewMode === "grid" ? "primary" : "ghost"}
              size="sm"
              onClick={() => setViewMode("grid")}
              aria-label="Grid view"
              aria-pressed={viewMode === "grid"}
            >
              <Grid className="h-4 w-4" />
            </Button>
            <Button
              variant={viewMode === "table" ? "primary" : "ghost"}
              size="sm"
              onClick={() => setViewMode("table")}
              aria-label="Table view"
              aria-pressed={viewMode === "table"}
            >
              <List className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Suppliers list */}
        {suppliersLoading ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <Skeleton key={i} variant="rectangular" height={240} />
            ))}
          </div>
        ) : viewMode === "grid" ? (
          <div
            className="grid gap-4 md:grid-cols-2 lg:grid-cols-3"
            aria-live="polite"
          >
            {suppliers.map((supplier) => (
              <SupplierCard
                key={supplier.id}
                supplier={supplier}
                isCurrent={supplier.id === currentSupplier?.id}
                currentAnnualCost={currentSupplier?.estimatedAnnualCost}
                showDetails
                onSelect={handleSelectSupplier}
              />
            ))}
          </div>
        ) : (
          <div aria-live="polite">
            <ComparisonTable
              suppliers={suppliers}
              currentSupplierId={currentSupplier?.id}
              showFilters
              onSelect={handleSelectSupplier}
            />
          </div>
        )}

        {/* Next step prompt — visible when user has a supplier set */}
        {currentSupplier && (
          <div className="mt-6 rounded-lg border border-primary-200 bg-primary-50 p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Link2 className="h-5 w-5 text-primary-600" />
                <div>
                  <p className="font-medium text-gray-900">
                    Next: Connect your utility account
                  </p>
                  <p className="text-sm text-gray-500">
                    Link your {currentSupplier.name} account for automatic rate
                    tracking.
                  </p>
                </div>
              </div>
              <Link href="/connections">
                <Button variant="primary" size="sm">
                  Set up Connection
                  <ArrowRight className="ml-1 h-4 w-4" />
                </Button>
              </Link>
            </div>
          </div>
        )}

        {/* Switch wizard modal (when user has a current supplier) */}
        {showWizard && wizardRecommendation && (
          <FocusTrapOverlay onClose={closeWizard} ariaLabel="Switch supplier">
            <SwitchWizard
              recommendation={wizardRecommendation}
              onComplete={handleSwitchComplete}
              onCancel={closeWizard}
            />
          </FocusTrapOverlay>
        )}

        {/* Set supplier dialog (first-time selection, no current supplier) */}
        {showSetDialog && (
          <FocusTrapOverlay
            onClose={closeSetDialog}
            ariaLabel="Set your current supplier"
            maxWidth="max-w-lg"
          >
            <SetSupplierDialog
              suppliers={suppliers}
              onSelect={handleSetSupplier}
              onCancel={closeSetDialog}
              isLoading={setSupplierMutation.isPending}
            />
          </FocusTrapOverlay>
        )}
      </div>
    </div>
  );
}
