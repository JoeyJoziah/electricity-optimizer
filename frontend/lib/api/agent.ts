/**
 * Agent API functions
 *
 * Query the RateShift AI assistant, submit async tasks,
 * and check usage limits.
 */

import { API_URL } from "@/lib/config/env";
import { apiClient } from "./client";
import { handle401Redirect } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AgentMessage {
  role: "user" | "assistant" | "error" | "tool";
  content: string;
  model_used?: string;
  tools_used?: string[];
  tokens_used?: number;
  duration_ms?: number;
  /** Client-generated unique ID for stable React keys */
  id?: string;
}

export interface AgentUsage {
  used: number;
  limit: number;
  remaining: number;
  tier: string;
}

export interface AgentTaskResponse {
  job_id: string;
}

export interface AgentJobResult {
  status: "processing" | "completed" | "failed" | "not_found";
  result?: string;
  model_used?: string;
  error?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let _msgCounter = 0;

/** Generate a unique client-side message ID */
export function generateMessageId(): string {
  _msgCounter += 1;
  return `msg-${Date.now()}-${_msgCounter}`;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/**
 * Query agent with SSE streaming.
 * Returns an async generator that yields AgentMessage objects.
 */
export async function* queryAgent(
  prompt: string,
  context?: Record<string, unknown>,
  signal?: AbortSignal,
): AsyncGenerator<AgentMessage> {
  const response = await fetch(`${API_URL}/agent/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ prompt, context }),
    signal,
  });

  if (!response.ok) {
    // Handle 401 using the shared redirect-loop protection from apiClient.
    // Previously this bypassed the safety valve (counter + dedup) and could
    // cause infinite redirect loops.
    if (response.status === 401) {
      if (handle401Redirect()) {
        // Redirect initiated -- stop yielding
        return;
      }
    }
    const errorData = await response.json().catch(() => ({}));
    yield {
      role: "error",
      content: errorData.detail || `Request failed (${response.status})`,
      id: generateMessageId(),
    };
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    yield {
      role: "error",
      content: "Streaming not supported",
      id: generateMessageId(),
    };
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6).trim();
        if (data === "[DONE]") return;
        try {
          const parsed = JSON.parse(data) as AgentMessage;
          parsed.id = parsed.id ?? generateMessageId();
          yield parsed;
        } catch {
          // skip malformed lines
        }
      }
    }
  }
}

/**
 * Submit an async agent task (for tool-heavy queries)
 */
export async function submitAgentTask(
  prompt: string,
  context?: Record<string, unknown>,
): Promise<AgentTaskResponse> {
  return apiClient.post<AgentTaskResponse>("/agent/task", { prompt, context });
}

/**
 * Poll result of an async agent task
 */
export async function getTaskResult(
  jobId: string,
  signal?: AbortSignal,
): Promise<AgentJobResult> {
  return apiClient.get<AgentJobResult>(`/agent/task/${jobId}`, undefined, {
    signal,
  });
}

/**
 * Get current agent usage stats
 */
export async function getAgentUsage(signal?: AbortSignal): Promise<AgentUsage> {
  return apiClient.get<AgentUsage>("/agent/usage", undefined, { signal });
}
