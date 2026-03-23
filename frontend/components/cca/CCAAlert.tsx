"use client";

import { useCCADetect } from "@/lib/hooks/useCCA";
import { useSettingsStore } from "@/lib/store/settings";
import { isSafeHref } from "@/lib/utils/url";

interface CCAAlertProps {
  onViewDetails?: (ccaId: string) => void;
  onDismiss?: () => void;
}

export function CCAAlert({ onViewDetails, onDismiss }: CCAAlertProps) {
  const region = useSettingsStore((s) => s.region);
  const stateCode = region ? region.slice(3).toUpperCase() : undefined;

  const { data, isLoading } = useCCADetect(undefined, stateCode);

  if (isLoading || !data?.in_cca || !data.program) return null;

  const program = data.program;

  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-blue-900">
            You&apos;re in a CCA Program
          </h3>
          <p className="mt-1 text-sm text-blue-700">
            <strong>{program.program_name}</strong> by {program.provider} serves
            your area ({program.municipality}, {program.state}).
          </p>
          {program.rate_vs_default_pct !== null &&
            program.rate_vs_default_pct < 0 && (
              <p className="mt-1 text-sm font-medium text-green-700">
                {Math.abs(program.rate_vs_default_pct)}% lower than default
                utility rate
              </p>
            )}
          <div className="mt-2 flex gap-2">
            {onViewDetails && (
              <button
                onClick={() => onViewDetails(program.id)}
                className="text-sm font-medium text-blue-700 hover:text-blue-900"
              >
                View Details
              </button>
            )}
            {program.program_url && isSafeHref(program.program_url) && (
              <a
                href={program.program_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-medium text-blue-700 hover:text-blue-900"
              >
                Program Website
              </a>
            )}
          </div>
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="ml-2 text-blue-400 hover:text-blue-600"
            aria-label="Dismiss CCA alert"
          >
            &times;
          </button>
        )}
      </div>
    </div>
  );
}
