/**
 * Drip email enrollment helper.
 * Isolated from Better Auth imports so it can be tested in Jest without
 * mocking the entire server-auth initialization chain.
 */

/**
 * Enroll a newly created user in the drip email sequence.
 * Fire-and-forget: any failure is swallowed so sign-up is never blocked.
 */
export async function enrollUserInDrip(
  userId: string,
  email: string,
  name: string | null,
): Promise<void> {
  const backendUrl = process.env.BACKEND_URL;
  const apiKey = process.env.INTERNAL_API_KEY;
  if (!backendUrl || !apiKey) return;
  try {
    await fetch(`${backendUrl}/api/v1/internal/drip/enroll`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": apiKey,
      },
      body: JSON.stringify({ user_id: userId, email, name }),
      signal: AbortSignal.timeout(5000),
    });
  } catch {
    // Enrollment failure must never surface to the user
  }
}
