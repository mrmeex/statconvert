import type {
  ApiErrorPayload,
  JobCreated,
  JobSnapshot,
  PlanResponse,
} from "./types";

export interface HealthResponse {
  status: "ok";
}

export interface VersionResponse {
  version: string;
  app_name: string;
  license: string;
}

export interface ShellStatus {
  version: string;
  license: string;
}

export class ApiError extends Error {
  readonly code: string;
  readonly suggestion?: string | null;

  constructor(payload: ApiErrorPayload, status: number) {
    super(payload.error.message || `Request failed with status ${status}.`);
    this.name = "ApiError";
    this.code = payload.error.code;
    this.suggestion = payload.error.suggestion;
  }
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  const payload = (await response.json()) as T | ApiErrorPayload;
  if (!response.ok) {
    throw new ApiError(payload as ApiErrorPayload, response.status);
  }
  return payload as T;
}

export function getJson<T>(path: string): Promise<T> {
  return requestJson<T>(path);
}

export function postJson<T>(
  path: string,
  payload: Record<string, unknown>,
): Promise<T> {
  return requestJson<T>(path, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function putJson<T>(
  path: string,
  payload: Record<string, unknown>,
): Promise<T> {
  return requestJson<T>(path, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getJob(jobId: string): Promise<JobSnapshot> {
  return requestJson<JobSnapshot>(`/api/jobs/${jobId}`);
}

export function getActiveJob(workflow: string): Promise<{ data: JobSnapshot | null }> {
  return requestJson<{ data: JobSnapshot | null }>(`/api/jobs/active?workflow=${encodeURIComponent(workflow)}`);
}

export function cancelJob(jobId: string): Promise<JobSnapshot> {
  return requestJson<JobSnapshot>(`/api/jobs/${jobId}/cancel`, {
    method: "POST",
  });
}

export function planWorkflow(
  workflow: "convert" | "batch" | "validate" | "compare" | "report" | "collect",
  payload: Record<string, unknown>,
): Promise<PlanResponse> {
  return postJson<PlanResponse>(`/api/workflows/plan-${workflow}`, payload);
}

export function executeWorkflow(
  workflow: "convert" | "batch" | "validate" | "transform" | "compare" | "report" | "collect",
  payload: Record<string, unknown>,
): Promise<JobCreated> {
  return postJson<JobCreated>(`/api/execute/${workflow}`, payload);
}

export async function fetchShellStatus(
  signal: AbortSignal,
): Promise<ShellStatus> {
  const [health, version] = await Promise.all([
    requestJson<HealthResponse>("/api/health", { signal }),
    requestJson<VersionResponse>("/api/version", { signal }),
  ]);
  if (health.status !== "ok") {
    throw new Error("The local StatConvert server is not ready.");
  }
  return {
    version: version.version,
    license: version.license,
  };
}
