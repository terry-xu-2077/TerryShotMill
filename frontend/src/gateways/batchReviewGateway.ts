export type PromptReviewStatus = "not_ready" | "pending_review" | "approved";

export type PromptReviewItem = {
  taskId: string;
  promptReviewStatus: PromptReviewStatus;
  approvedRevision?: number;
};

export type PromptReviewState = {
  items: PromptReviewItem[];
};

export type BatchPromptRequest = {
  taskIds: string[];
  includeProjectBackground: boolean;
  includePreviousTaskSummary: boolean;
};

export type BatchPromptResponse = {
  batchId: string;
  state: "queued" | "running" | "completed" | "partial" | "failed" | "cancelled";
  items: Array<{
    taskId: string;
    state: "completed" | "failed" | "skipped";
    revisionId?: string;
    error?: string;
  }>;
};

export type VideoBatchEligibility = {
  eligibleTaskIds: string[];
  skipped: Array<{
    taskId: string;
    reason: "not-reviewed" | "busy" | "invalid-params" | string;
  }>;
};

export type VideoBatchResponse = VideoBatchEligibility & {
  batchId: string;
};

const configuredApiBase = import.meta.env.VITE_SHOTMILL_API_BASE_URL?.trim();
const API_BASE = (configuredApiBase || "/api/v1").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const error = new Error(`Batch review request failed (${response.status})`);
    Object.assign(error, { status: response.status });
    throw error;
  }
  return response.json() as Promise<T>;
}

export class BatchReviewGateway {
  getPromptReviewState(projectId: string) {
    return request<PromptReviewState>(
      `/projects/${encodeURIComponent(projectId)}/prompt-review-state`,
    );
  }

  batchEnhancePrompts(projectId: string, input: BatchPromptRequest) {
    return request<BatchPromptResponse>(
      `/projects/${encodeURIComponent(projectId)}/prompt-enhancement-batches`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      },
    );
  }

  getPromptEnhancementBatch(projectId: string, batchId: string) {
    return request<BatchPromptResponse>(
      `/projects/${encodeURIComponent(projectId)}/prompt-enhancement-batches/${encodeURIComponent(batchId)}`,
    );
  }

  approvePrompt(projectId: string, taskId: string) {
    return request<PromptReviewItem>(
      `/projects/${encodeURIComponent(projectId)}/tasks/${encodeURIComponent(taskId)}/prompt-review`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "approve" }),
      },
    );
  }

  checkVideoBatchEligibility(projectId: string, taskIds: string[]) {
    return request<VideoBatchEligibility>(
      `/projects/${encodeURIComponent(projectId)}/video-generation-batches/eligibility`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ taskIds }),
      },
    );
  }

  createVideoBatch(projectId: string, taskIds: string[]) {
    return request<VideoBatchResponse>(
      `/projects/${encodeURIComponent(projectId)}/video-generation-batches`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ taskIds }),
      },
    );
  }
}

export const batchReviewGateway = new BatchReviewGateway();
