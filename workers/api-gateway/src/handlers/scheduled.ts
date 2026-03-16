import type { Env } from "../types";

/**
 * CF Worker Cron Trigger handler for check-alerts.
 * Replaces the GHA cron workflow — runs every 3 hours.
 * Includes one retry after 35s to handle Render cold starts.
 */
export async function handleScheduled(
  controller: ScheduledController,
  env: Env,
  ctx: ExecutionContext
): Promise<void> {
  const originUrl = `${env.ORIGIN_URL}/api/v1/internal/check-alerts`;

  const doFetch = async (): Promise<Response> => {
    return fetch(originUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": env.INTERNAL_API_KEY ?? "",
      },
      body: "{}",
    });
  };

  try {
    let response = await doFetch();

    // Retry once after 35s if the origin is waking up (502/503/504)
    if (response.status >= 502 && response.status <= 504) {
      console.log(
        `check-alerts: origin returned ${response.status}, retrying in 35s (Render cold start)`
      );
      await new Promise((resolve) => setTimeout(resolve, 35_000));
      response = await doFetch();
    }

    if (!response.ok) {
      console.error(
        `check-alerts failed: ${response.status} ${response.statusText}`
      );
    } else {
      console.log("check-alerts completed successfully");
    }
  } catch (err) {
    console.error(
      "check-alerts fetch error:",
      err instanceof Error ? err.message : err
    );
  }
}
