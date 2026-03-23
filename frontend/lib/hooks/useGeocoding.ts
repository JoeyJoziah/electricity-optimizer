"use client";

import { useState, useCallback, useRef } from "react";
import { apiClient } from "@/lib/api/client";

interface GeocodeResult {
  lat: number;
  lng: number;
  state: string | null;
  formatted_address: string | null;
}

interface GeocodeResponse {
  result: GeocodeResult | null;
}

export function useGeocoding() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Track the latest request so out-of-order responses are discarded.
  const requestIdRef = useRef(0);
  // AbortController to cancel the previous in-flight request when a new
  // one is issued, preventing stale results from overwriting fresh ones.
  const abortControllerRef = useRef<AbortController | null>(null);

  const geocode = useCallback(
    async (address: string): Promise<GeocodeResult | null> => {
      // Cancel any previous in-flight request
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }

      const controller = new AbortController();
      abortControllerRef.current = controller;

      // Increment and capture this request's ID
      const currentRequestId = ++requestIdRef.current;

      setLoading(true);
      setError(null);
      try {
        const data = await apiClient.post<GeocodeResponse>(
          "/geocode",
          { address },
          { signal: controller.signal },
        );

        // If a newer request has been issued while we were awaiting, discard
        // this response to avoid showing stale results.
        if (currentRequestId !== requestIdRef.current) {
          return null;
        }

        setLoading(false);
        return data.result ?? null;
      } catch (e) {
        // Silently discard AbortErrors — they are expected when a newer
        // request cancels this one.
        if (e instanceof DOMException && e.name === "AbortError") {
          return null;
        }

        // Only update state if this is still the latest request
        if (currentRequestId === requestIdRef.current) {
          setError(e instanceof Error ? e.message : "Geocoding failed");
          setLoading(false);
        }
        return null;
      }
    },
    [],
  );

  return { geocode, loading, error };
}
