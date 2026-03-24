import type { Env } from "../types";

/**
 * CF Worker Cron Trigger handler for scheduled tasks.
 * Routes based on the cron expression that triggered the event.
 *
 * Cron schedule:
 *   "*​/10 * * * *" → keep-alive (every 10 minutes — prevents Render cold starts)
 *   "0 *​/3 * * *"  → check-alerts (every 3 hours)
 *   "0 *​/6 * * *"  → price-sync (every 6 hours)
 *   "30 *​/6 * * *" → observe-forecasts (30min after price-sync)
 *
 * Includes one retry after 35s to handle Render cold starts.
 */
export async function handleScheduled(
  controller: ScheduledController,
  env: Env,
  ctx: ExecutionContext
): Promise<void> {
  const cron = controller.cron;

  // Route to the appropriate endpoint based on cron expression
  // Keep-alive: lightweight GET to root — prevents Render free tier spin-down
  if (cron === "*/10 * * * *") {
    try {
      const resp = await fetch(`${env.ORIGIN_URL}/`, { method: "GET" });
      console.log(`keep-alive: ${resp.status} (${resp.ok ? "ok" : "degraded"})`);
    } catch (err) {
      console.warn(`keep-alive: fetch error — ${err instanceof Error ? err.message : err}`);
    }
    return;
  }

  const cronRoutes: Record<string, { endpoint: string; name: string; method: string }> = {
    "0 */3 * * *": {
      endpoint: "/api/v1/internal/check-alerts",
      name: "check-alerts",
      method: "POST",
    },
    "0 */6 * * *": {
      endpoint: "/api/v1/prices/refresh",
      name: "price-sync",
      method: "POST",
    },
    "30 */6 * * *": {
      endpoint: "/api/v1/internal/observe-forecasts",
      name: "observe-forecasts",
      method: "POST",
    },
  };

  const route = cronRoutes[cron];
  if (!route) {
    console.error(`Unknown cron expression: ${cron}`);
    return;
  }

  // Fail-closed: abort if INTERNAL_API_KEY is not configured rather than
  // sending unauthenticated requests to internal endpoints.
  if (!env.INTERNAL_API_KEY) {
    console.error(
      `${route.name}: INTERNAL_API_KEY not configured — aborting scheduled task`
    );
    return;
  }

  const originUrl = `${env.ORIGIN_URL}${route.endpoint}`;
  console.log(`${route.name}: triggering ${route.method} ${route.endpoint}`);

  const doFetch = async (): Promise<Response> => {
    return fetch(originUrl, {
      method: route.method,
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": env.INTERNAL_API_KEY!,
      },
      body: route.method === "POST" ? "{}" : undefined,
    });
  };

  try {
    let response = await doFetch();

    // Retry once after 35s if the origin is waking up (502/503/504)
    if (response.status >= 502 && response.status <= 504) {
      console.log(
        `${route.name}: origin returned ${response.status}, retrying in 35s (Render cold start)`
      );
      await new Promise((resolve) => setTimeout(resolve, 35_000));
      response = await doFetch();
    }

    if (!response.ok) {
      console.error(
        `${route.name} failed: ${response.status} ${response.statusText}`
      );
    } else {
      console.log(`${route.name} completed successfully`);
    }
  } catch (err) {
    console.error(
      `${route.name} fetch error:`,
      err instanceof Error ? err.message : err
    );
  }
}
