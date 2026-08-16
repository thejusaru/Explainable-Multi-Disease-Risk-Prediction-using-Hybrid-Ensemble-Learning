import type {
  AnalyzeResponse,
  EnginesResponse,
  EngineKind,
  ExtractResponse,
  PatientProfile,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

/** Error carrying the backend's message so the UI can show something useful. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  let detail = `Request failed with status ${response.status}`;
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") {
      detail = body.detail;
    } else if (Array.isArray(body?.detail)) {
      // FastAPI validation errors arrive as a list of per-field objects.
      detail = body.detail
        .map((item: { loc?: string[]; msg?: string }) => {
          const field = item.loc?.filter((p) => p !== "body").join(".") ?? "";
          return field ? `${field}: ${item.msg}` : item.msg;
        })
        .filter(Boolean)
        .join("; ");
    }
  } catch {
    // Non-JSON error body (proxy timeout, HTML error page) — keep the default.
  }
  return new ApiError(detail, response.status);
}

export interface EngineSelection {
  engine?: EngineKind;
  model?: string;
}

/** Context carried over from a prior extract call, so the file isn't re-sent. */
export interface ReportContext {
  report_text?: string | null;
  image_base64?: string | null;
  image_media_type?: string | null;
}

/** Read a report and return what was found, without running an assessment. */
export async function extractReport(file: File): Promise<ExtractResponse> {
  const form = new FormData();
  form.append("file", file);

  const response = await fetch(`${API_BASE}/api/extract`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) throw await toApiError(response);
  return response.json();
}

export async function analyzeProfile(
  profile: PatientProfile,
  selection: EngineSelection = {},
  context: ReportContext = {},
): Promise<AnalyzeResponse> {
  const response = await fetch(`${API_BASE}/api/analyze/profile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      profile,
      engine: selection.engine ?? null,
      model: selection.model ?? null,
      report_text: context.report_text ?? null,
      image_base64: context.image_base64 ?? null,
      image_media_type: context.image_media_type ?? null,
    }),
  });
  if (!response.ok) throw await toApiError(response);
  return response.json();
}

export async function analyzeReport(
  file: File,
  profile?: Partial<PatientProfile>,
  selection: EngineSelection = {},
): Promise<AnalyzeResponse> {
  const form = new FormData();
  form.append("file", file);
  if (profile && Object.keys(profile).length > 0) {
    form.append("profile_json", JSON.stringify(profile));
  }

  // Engine selection rides in the query string — the body is multipart.
  const params = new URLSearchParams();
  if (selection.engine) params.set("engine", selection.engine);
  if (selection.model) params.set("model", selection.model);
  const query = params.toString();

  const response = await fetch(
    `${API_BASE}/api/analyze/report${query ? `?${query}` : ""}`,
    { method: "POST", body: form },
  );
  if (!response.ok) throw await toApiError(response);
  return response.json();
}

export async function listEngines(): Promise<EnginesResponse> {
  const response = await fetch(`${API_BASE}/api/engines`);
  if (!response.ok) throw await toApiError(response);
  return response.json();
}

export async function checkHealth(): Promise<{
  status: string;
  model: string;
  credentials_detected: boolean;
}> {
  const response = await fetch(`${API_BASE}/api/health`);
  if (!response.ok) throw await toApiError(response);
  return response.json();
}
