"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Header } from "@/components/layout/Header";
import { Card, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/lib/contexts/toast-context";
import { cn } from "@/lib/utils/cn";
import {
  getSettings,
  updateSettings,
  signLOA,
  revokeLOA,
} from "@/lib/api/agent-switcher";
import type {
  AgentSettings,
  AgentSettingsUpdate,
} from "@/lib/api/agent-switcher";
import {
  ArrowLeft,
  ShieldCheck,
  ShieldOff,
  Calendar,
  Clock,
  TrendingUp,
  Power,
  FileText,
  X,
  AlertTriangle,
} from "lucide-react";
import Link from "next/link";

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

const settingsKeys = {
  all: ["agent-switcher-settings"] as const,
};

// ---------------------------------------------------------------------------
// Toggle Switch (inline, no external dependency)
// ---------------------------------------------------------------------------

interface ToggleSwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
  size?: "md" | "lg";
}

function ToggleSwitch({
  checked,
  onChange,
  disabled,
  id,
  size = "md",
  ...rest
}: ToggleSwitchProps) {
  const sizeClasses =
    size === "lg"
      ? { track: "h-8 w-14", thumb: "h-6 w-6", translate: "translate-x-6" }
      : { track: "h-6 w-11", thumb: "h-4 w-4", translate: "translate-x-5" };

  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
      className={cn(
        "relative inline-flex shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2",
        "disabled:cursor-not-allowed disabled:opacity-50",
        sizeClasses.track,
        checked ? "bg-primary-600" : "bg-gray-200",
      )}
      {...rest}
    >
      <span
        className={cn(
          "pointer-events-none inline-block rounded-full bg-white shadow ring-0 transition-transform duration-200 ease-in-out",
          sizeClasses.thumb,
          checked ? sizeClasses.translate : "translate-x-1",
        )}
      />
    </button>
  );
}

// ---------------------------------------------------------------------------
// Debounced save hook
// ---------------------------------------------------------------------------

function useDebouncedSave() {
  const queryClient = useQueryClient();
  const { success, error: toastError } = useToast();
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const mutation = useMutation({
    mutationFn: (patch: AgentSettingsUpdate) => updateSettings(patch),
    onSuccess: (data) => {
      queryClient.setQueryData(settingsKeys.all, data);
      success("Settings saved");
    },
    onError: () => {
      toastError("Failed to save settings", "Please try again.");
    },
  });

  const save = useCallback(
    (patch: AgentSettingsUpdate, immediate = false) => {
      if (timerRef.current) clearTimeout(timerRef.current);

      if (immediate) {
        mutation.mutate(patch);
        return;
      }

      timerRef.current = setTimeout(() => {
        mutation.mutate(patch);
      }, 600);
    },
    [mutation],
  );

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return { save, isSaving: mutation.isPending };
}

// ---------------------------------------------------------------------------
// KillSwitch Section
// ---------------------------------------------------------------------------

function KillSwitchSection({
  enabled,
  onToggle,
  disabled,
}: {
  enabled: boolean;
  onToggle: (v: boolean) => void;
  disabled: boolean;
}) {
  return (
    <Card variant="bordered" padding="lg">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3 min-w-0">
          <div
            className={cn(
              "mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
              enabled ? "bg-success-50" : "bg-gray-100",
            )}
          >
            <Power
              className={cn(
                "h-5 w-5",
                enabled ? "text-success-600" : "text-gray-400",
              )}
            />
          </div>
          <div>
            <CardTitle as="h2">Enable Auto Rate Switcher</CardTitle>
            <CardDescription className="mt-1">
              {enabled
                ? "The auto-switcher is actively monitoring your rates and will switch plans when savings thresholds are met."
                : "When enabled, the auto-switcher agent will continuously monitor electricity rates in your region and automatically switch you to cheaper plans."}
            </CardDescription>
          </div>
        </div>
        <ToggleSwitch
          checked={enabled}
          onChange={onToggle}
          disabled={disabled}
          size="lg"
          aria-label="Enable auto rate switcher"
        />
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Savings Threshold Section
// ---------------------------------------------------------------------------

function SavingsThresholdSection({
  pct,
  min,
  onPctChange,
  onMinChange,
  disabled,
}: {
  pct: number;
  min: number;
  onPctChange: (v: number) => void;
  onMinChange: (v: number) => void;
  disabled: boolean;
}) {
  return (
    <Card variant="bordered" padding="lg">
      <div className="flex items-start gap-3 mb-5">
        <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary-50">
          <TrendingUp className="h-5 w-5 text-primary-600" />
        </div>
        <div>
          <CardTitle as="h2">Savings Threshold</CardTitle>
          <CardDescription className="mt-1">
            A switch will only be executed when the projected savings exceed
            <strong> either </strong>
            the percentage or dollar threshold below.
          </CardDescription>
        </div>
      </div>

      <div className="space-y-6">
        {/* Percentage slider */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label
              htmlFor="savings-pct"
              className="text-sm font-medium text-gray-700"
            >
              Minimum savings percentage
            </label>
            <span className="text-sm font-semibold text-primary-600">
              {pct}%
            </span>
          </div>
          <input
            id="savings-pct"
            type="range"
            min={1}
            max={50}
            step={1}
            value={pct}
            onChange={(e) => onPctChange(Number(e.target.value))}
            disabled={disabled}
            className={cn(
              "w-full h-2 rounded-full appearance-none cursor-pointer",
              "bg-gray-200 accent-primary-600",
              "disabled:cursor-not-allowed disabled:opacity-50",
            )}
            aria-valuemin={1}
            aria-valuemax={50}
            aria-valuenow={pct}
            aria-valuetext={`${pct} percent`}
          />
          <div className="flex justify-between mt-1">
            <span className="text-xs text-gray-400">1%</span>
            <span className="text-xs text-gray-400">50%</span>
          </div>
        </div>

        {/* Dollar amount */}
        <div className="max-w-xs">
          <Input
            id="savings-min-dollar"
            label="Minimum dollar savings"
            type="number"
            min={1}
            max={100}
            step={1}
            value={min}
            onChange={(e) => {
              const val = Number(e.target.value);
              if (val >= 1 && val <= 100) onMinChange(val);
            }}
            disabled={disabled}
            helperText="Monthly savings must exceed this amount ($1 - $100)"
            aria-valuemin={1}
            aria-valuemax={100}
          />
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Cooldown Section
// ---------------------------------------------------------------------------

function CooldownSection({
  days,
  onChange,
  disabled,
}: {
  days: number;
  onChange: (v: number) => void;
  disabled: boolean;
}) {
  return (
    <Card variant="bordered" padding="lg">
      <div className="flex items-start gap-3 mb-5">
        <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-warning-50">
          <Clock className="h-5 w-5 text-warning-600" />
        </div>
        <div>
          <CardTitle as="h2">Post-Switch Cooldown</CardTitle>
          <CardDescription className="mt-1">
            After a switch is executed, the agent will wait this many days
            before evaluating new switch opportunities. This prevents excessive
            plan-hopping and allows time for the new plan to take effect.
          </CardDescription>
        </div>
      </div>

      <div className="max-w-xs">
        <Input
          id="cooldown-days"
          label="Cooldown period"
          labelSuffix="(days)"
          type="number"
          min={1}
          max={30}
          step={1}
          value={days}
          onChange={(e) => {
            const val = Number(e.target.value);
            if (val >= 1 && val <= 30) onChange(val);
          }}
          disabled={disabled}
          helperText="1 to 30 days"
        />
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Pause Until Section
// ---------------------------------------------------------------------------

function PauseUntilSection({
  pausedUntil,
  onDateChange,
  onClear,
  disabled,
}: {
  pausedUntil: string | null;
  onDateChange: (v: string) => void;
  onClear: () => void;
  disabled: boolean;
}) {
  const isPaused = !!pausedUntil;
  const pauseDate = pausedUntil ? new Date(pausedUntil) : null;
  const isPastDate = pauseDate ? pauseDate < new Date() : false;

  // Minimum date is tomorrow
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const minDate = tomorrow.toISOString().split("T")[0];

  return (
    <Card variant="bordered" padding="lg">
      <div className="flex items-start gap-3 mb-5">
        <div
          className={cn(
            "mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
            isPaused && !isPastDate ? "bg-warning-50" : "bg-gray-100",
          )}
        >
          <Calendar
            className={cn(
              "h-5 w-5",
              isPaused && !isPastDate ? "text-warning-600" : "text-gray-400",
            )}
          />
        </div>
        <div>
          <CardTitle as="h2">Temporary Pause</CardTitle>
          <CardDescription className="mt-1">
            Temporarily pause the auto-switcher until a specific date. The agent
            will resume monitoring automatically after this date.
          </CardDescription>
        </div>
      </div>

      <div className="flex items-end gap-3">
        <div className="max-w-xs">
          <Input
            id="pause-until"
            label="Pause until"
            type="date"
            min={minDate}
            value={pausedUntil ? pausedUntil.split("T")[0] : ""}
            onChange={(e) => {
              if (e.target.value) {
                onDateChange(e.target.value + "T00:00:00Z");
              }
            }}
            disabled={disabled}
          />
        </div>

        {isPaused && (
          <Button
            variant="outline"
            size="sm"
            onClick={onClear}
            disabled={disabled}
            leftIcon={<X className="h-4 w-4" />}
          >
            Unpause
          </Button>
        )}
      </div>

      {isPaused && !isPastDate && (
        <p className="mt-3 text-sm text-warning-600">
          The auto-switcher is paused until{" "}
          {pauseDate!.toLocaleDateString("en-US", {
            weekday: "long",
            year: "numeric",
            month: "long",
            day: "numeric",
          })}
          .
        </p>
      )}

      {isPaused && isPastDate && (
        <p className="mt-3 text-sm text-gray-500">
          The pause date has passed. The auto-switcher is active. Clear the date
          to remove this notice.
        </p>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// LOA Section
// ---------------------------------------------------------------------------

function LOASection({
  loaSigned,
  loaRevoked,
  settings,
  disabled,
}: {
  loaSigned: boolean;
  loaRevoked: boolean;
  settings: AgentSettings | undefined;
  disabled: boolean;
}) {
  const queryClient = useQueryClient();
  const { success, error: toastError } = useToast();
  const [showRevokeModal, setShowRevokeModal] = useState(false);

  const signMutation = useMutation({
    mutationFn: signLOA,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: settingsKeys.all });
      success(
        "LOA signed successfully",
        "The auto-switcher agent can now execute plan switches on your behalf.",
      );
    },
    onError: () => {
      toastError("Failed to sign LOA", "Please try again.");
    },
  });

  const revokeMutation = useMutation({
    mutationFn: revokeLOA,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: settingsKeys.all });
      success(
        "LOA revoked",
        "The auto-switcher agent will no longer execute switches automatically.",
      );
    },
    onError: () => {
      toastError("Failed to revoke LOA", "Please try again.");
    },
  });

  const isActive = loaSigned && !loaRevoked;

  return (
    <>
      <Card variant="bordered" padding="lg">
        <div className="flex items-start gap-3 mb-5">
          <div
            className={cn(
              "mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
              isActive ? "bg-success-50" : "bg-gray-100",
            )}
          >
            {isActive ? (
              <ShieldCheck className="h-5 w-5 text-success-600" />
            ) : (
              <FileText className="h-5 w-5 text-gray-400" />
            )}
          </div>
          <div>
            <CardTitle as="h2">Letter of Authorization (LOA)</CardTitle>
            <CardDescription className="mt-1">
              The LOA grants the auto-switcher agent permission to execute plan
              switches on your behalf. Without a signed LOA, the agent can only
              recommend switches for your manual approval.
            </CardDescription>
          </div>
        </div>

        {isActive ? (
          <div className="space-y-4">
            <div className="flex items-center gap-2 rounded-lg bg-success-50 px-4 py-3">
              <ShieldCheck className="h-5 w-5 text-success-600 shrink-0" />
              <div>
                <p className="text-sm font-medium text-success-800">
                  LOA is active
                </p>
                {settings?.updated_at && (
                  <p className="text-xs text-success-600">
                    Signed on{" "}
                    {new Date(settings.updated_at).toLocaleDateString("en-US", {
                      year: "numeric",
                      month: "long",
                      day: "numeric",
                    })}
                  </p>
                )}
              </div>
            </div>

            <div className="flex items-start gap-2 rounded-lg border border-warning-200 bg-warning-50 px-4 py-3">
              <AlertTriangle className="h-5 w-5 text-warning-600 shrink-0 mt-0.5" />
              <p className="text-sm text-warning-700">
                Revoking the LOA will immediately stop the agent from executing
                any new switches. Pending switches that have not yet been
                confirmed will also be cancelled.
              </p>
            </div>

            <Button
              variant="danger"
              onClick={() => setShowRevokeModal(true)}
              disabled={disabled || revokeMutation.isPending}
              loading={revokeMutation.isPending}
              leftIcon={<ShieldOff className="h-4 w-4" />}
            >
              Revoke LOA
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            {loaRevoked && (
              <div className="flex items-center gap-2 rounded-lg bg-gray-50 px-4 py-3">
                <ShieldOff className="h-5 w-5 text-gray-400 shrink-0" />
                <p className="text-sm text-gray-600">
                  Your LOA was previously revoked. You can sign a new one to
                  re-enable automatic switching.
                </p>
              </div>
            )}

            <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
              <p className="text-sm text-gray-600">
                By signing the LOA, you authorize RateShift to automatically
                change your electricity plan when the agent identifies a plan
                that meets your savings thresholds. You can revoke this
                authorization at any time.
              </p>
            </div>

            <Button
              variant="primary"
              onClick={() => signMutation.mutate()}
              disabled={disabled || signMutation.isPending}
              loading={signMutation.isPending}
              leftIcon={<ShieldCheck className="h-4 w-4" />}
            >
              Sign LOA
            </Button>
          </div>
        )}
      </Card>

      <Modal
        open={showRevokeModal}
        onClose={() => setShowRevokeModal(false)}
        title="Revoke Letter of Authorization"
        description="Are you sure you want to revoke your LOA? The auto-switcher agent will no longer be able to execute plan switches automatically. You will need to manually approve any recommended switches."
        confirmLabel="Revoke LOA"
        cancelLabel="Keep LOA"
        variant="danger"
        onConfirm={() => revokeMutation.mutate()}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// Main Content
// ---------------------------------------------------------------------------

export default function AutoSwitcherSettingsContent() {
  const {
    data: settings,
    isLoading,
    isError,
  } = useQuery({
    queryKey: settingsKeys.all,
    queryFn: ({ signal }) => getSettings(signal),
    staleTime: 30_000,
  });

  const { save, isSaving } = useDebouncedSave();

  // Local state mirrors server state, updated optimistically
  const [localEnabled, setLocalEnabled] = useState<boolean | null>(null);
  const [localPct, setLocalPct] = useState<number | null>(null);
  const [localMin, setLocalMin] = useState<number | null>(null);
  const [localCooldown, setLocalCooldown] = useState<number | null>(null);
  const [localPausedUntil, setLocalPausedUntil] = useState<
    string | null | undefined
  >(undefined);

  // Sync from server when data arrives
  useEffect(() => {
    if (settings) {
      if (localEnabled === null) setLocalEnabled(settings.enabled);
      if (localPct === null) setLocalPct(settings.savings_threshold_pct);
      if (localMin === null) setLocalMin(settings.savings_threshold_min);
      if (localCooldown === null) setLocalCooldown(settings.cooldown_days);
      if (localPausedUntil === undefined)
        setLocalPausedUntil(settings.paused_until);
    }
  }, [
    settings,
    localEnabled,
    localPct,
    localMin,
    localCooldown,
    localPausedUntil,
  ]);

  // Derived values (prefer local over server)
  const enabled = localEnabled ?? settings?.enabled ?? false;
  const pct = localPct ?? settings?.savings_threshold_pct ?? 10;
  const min = localMin ?? settings?.savings_threshold_min ?? 10;
  const cooldown = localCooldown ?? settings?.cooldown_days ?? 5;
  const pausedUntil =
    localPausedUntil !== undefined
      ? localPausedUntil
      : (settings?.paused_until ?? null);

  // -- Handlers --

  const handleToggle = (v: boolean) => {
    setLocalEnabled(v);
    save({ enabled: v }, true);
  };

  const handlePctChange = (v: number) => {
    setLocalPct(v);
    save({ savings_threshold_pct: v });
  };

  const handleMinChange = (v: number) => {
    setLocalMin(v);
    save({ savings_threshold_min: v });
  };

  const handleCooldownChange = (v: number) => {
    setLocalCooldown(v);
    save({ cooldown_days: v });
  };

  const handlePauseChange = (v: string) => {
    setLocalPausedUntil(v);
    save({ paused_until: v }, true);
  };

  const handlePauseClear = () => {
    setLocalPausedUntil(null);
    save({ paused_until: null }, true);
  };

  // -- Loading state --

  if (isLoading) {
    return (
      <>
        <Header title="Auto Switcher Settings" />
        <div className="p-4 lg:p-6 space-y-6">
          {[1, 2, 3, 4, 5].map((i) => (
            <div
              key={i}
              className="rounded-xl border border-gray-200 bg-white p-6 space-y-3"
            >
              <Skeleton variant="text" className="h-6 w-48" />
              <Skeleton variant="text" className="h-4 w-full" />
              <Skeleton variant="rectangular" className="h-10 w-40" />
            </div>
          ))}
        </div>
      </>
    );
  }

  if (isError) {
    return (
      <>
        <Header title="Auto Switcher Settings" />
        <div className="flex h-96 items-center justify-center">
          <div className="text-center">
            <h2 className="text-lg font-semibold text-gray-900">
              Unable to load settings
            </h2>
            <p className="mt-2 text-sm text-gray-500">
              We could not retrieve your auto-switcher settings. Please try
              again later.
            </p>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <Header title="Auto Switcher Settings" />

      <div className="p-4 lg:p-6">
        {/* Back link */}
        <div className="mb-6">
          <Link
            href="/auto-switcher"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Auto Switcher
          </Link>
        </div>

        {/* Saving indicator */}
        {isSaving && (
          <div className="mb-4 flex items-center gap-2 text-sm text-gray-500">
            <div className="h-3 w-3 animate-spin rounded-full border-2 border-gray-300 border-t-primary-600" />
            Saving...
          </div>
        )}

        <div className="space-y-6 max-w-3xl">
          <KillSwitchSection
            enabled={enabled}
            onToggle={handleToggle}
            disabled={isSaving}
          />

          <SavingsThresholdSection
            pct={pct}
            min={min}
            onPctChange={handlePctChange}
            onMinChange={handleMinChange}
            disabled={!enabled || isSaving}
          />

          <CooldownSection
            days={cooldown}
            onChange={handleCooldownChange}
            disabled={!enabled || isSaving}
          />

          <PauseUntilSection
            pausedUntil={pausedUntil}
            onDateChange={handlePauseChange}
            onClear={handlePauseClear}
            disabled={!enabled || isSaving}
          />

          <LOASection
            loaSigned={settings?.loa_signed ?? false}
            loaRevoked={settings?.loa_revoked ?? false}
            settings={settings}
            disabled={!enabled || isSaving}
          />
        </div>
      </div>
    </>
  );
}
