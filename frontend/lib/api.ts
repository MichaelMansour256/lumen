import type {
  ApiErrorBody, EnhanceSettings, ExportFormat, ImageRecord, Job, Plan, SystemInfo,
} from "./types";

export const DEFAULT_API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const STORAGE_KEY = "lumen.connection";

export interface Connection { url: string; key: string }

let connection: Connection = { url: DEFAULT_API_URL, key: "" };

/** Load the saved server connection; a share link (#api=...&key=...) overrides it. */
export function initConnection(): Connection {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    if (saved && typeof saved.url === "string") connection = { url: saved.url, key: saved.key ?? "" };
  } catch {
    /* storage unavailable: keep defaults */
  }
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const api = hash.get("api");
  if (api || hash.get("key")) {
    setConnection({ url: api ?? connection.url, key: hash.get("key") ?? connection.key });
    // Remove the key from the address bar and history.
    history.replaceState(null, "", window.location.pathname + window.location.search);
  }
  return connection;
}

export function getConnection(): Connection {
  return connection;
}

export function setConnection(next: Connection) {
  connection = { url: normaliseUrl(next.url) || DEFAULT_API_URL, key: next.key.trim() };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(connection));
  } catch {
    /* ignore */
  }
}

export function normaliseUrl(url: string): string {
  const trimmed = url.trim().replace(/\/+$/, "");
  if (!trimmed) return "";
  return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
}

/** True when this page itself is served from somewhere other than this computer (e.g. Vercel). */
export const isHostedRemotely = () =>
  typeof window !== "undefined" && !/^(localhost|127\.0\.0\.1|\[::1\])$/i.test(window.location.hostname);

export const isLocalServer = () => /^https?:\/\/(127\.0\.0\.1|localhost)(:|\/|$)/i.test(connection.url);

function authHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  if (connection.key) headers.set("X-Access-Key", connection.key);
  return headers;
}

export class ApiError extends Error {
  code: string;
  retryable: boolean;
  details: ApiErrorBody["details"];

  constructor(body: Partial<ApiErrorBody> & { message: string }) {
    super(body.message);
    this.code = body.code ?? "error";
    this.retryable = body.retryable ?? false;
    this.details = body.details ?? {};
  }
}

const offlineMessage = () => isLocalServer()
  ? "Cannot reach the enhancement server. Make sure the backend is running (start.bat)."
  : "Cannot reach the enhancement server. It may be offline - ask its owner for a fresh link.";

async function send(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${connection.url}${path}`, { ...init, headers: authHeaders(init?.headers) });
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await send(path, init);
  } catch (err) {
    if ((err as Error)?.name === "AbortError") throw err;
    throw new ApiError({ code: "offline", message: offlineMessage(), retryable: true });
  }
  if (!res.ok) throw await toError(res);
  return (await res.json()) as T;
}

async function toError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    if (body?.error?.message) return new ApiError(body.error);
  } catch {
    /* not JSON */
  }
  return new ApiError({ code: "http_error", message: `Request failed (${res.status}).` });
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/** Fetch an image (with the access key) and return an object URL for <img>. */
export async function fetchImageUrl(path: string, signal?: AbortSignal): Promise<string> {
  let res: Response;
  try {
    res = await send(path, { signal });
  } catch (err) {
    if ((err as Error)?.name === "AbortError") throw err;
    throw new ApiError({ code: "offline", message: offlineMessage(), retryable: true });
  }
  if (!res.ok) throw await toError(res);
  return URL.createObjectURL(await res.blob());
}

export const getSystem = () => request<SystemInfo>("/api/system");

export async function uploadImages(files: File[]) {
  const form = new FormData();
  files.forEach((file) => form.append("files", file, file.name));
  return request<{ images: ImageRecord[]; errors: { name: string; error: ApiErrorBody }[] }>(
    "/api/images", { method: "POST", body: form });
}

export const deleteImage = (id: string) =>
  request<{ deleted: string }>(`/api/images/${id}`, { method: "DELETE" });

export const getPlan = (imageId: string, settings: EnhanceSettings, format: ExportFormat,
                        quality: number, signal?: AbortSignal) =>
  request<Plan>("/api/plan", { ...json({ image_id: imageId, settings, format, quality }), signal });

export const createJobs = (imageIds: string[], settings: EnhanceSettings) =>
  request<{ jobs: Job[]; errors: { image_id: string; error: ApiErrorBody }[] }>(
    "/api/jobs", json({ image_ids: imageIds, settings }));

export const getJobs = (ids: string[]) =>
  request<{ jobs: Job[] }>(`/api/jobs?ids=${ids.join(",")}`);

export const retryJob = (id: string, device?: "auto" | "cpu") =>
  request<Job>(`/api/jobs/${id}/retry${device ? `?device=${device}` : ""}`, { method: "POST" });

export const cancelJob = (id: string) =>
  request<{ cancelled: boolean }>(`/api/jobs/${id}/cancel`, { method: "POST" });

export const resultPath = (jobId: string) => `/api/jobs/${jobId}/result`;
export const previewPath = (jobId: string) => `/api/jobs/${jobId}/preview`;
export type Progress = (fraction: number | null) => void;

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

async function download(path: string, init: RequestInit | undefined, fallbackName: string, onProgress?: Progress) {
  let res: Response;
  try {
    res = await send(path, init);
  } catch {
    throw new ApiError({ code: "download_failed", message: "Download failed: the server did not respond.", retryable: true });
  }
  if (!res.ok) {
    const err = await toError(res);
    throw new ApiError({ code: err.code, message: `Download failed: ${err.message}`, retryable: true });
  }
  const total = Number(res.headers.get("Content-Length")) || 0;
  let blob: Blob;
  if (onProgress && res.body) {
    const reader = res.body.getReader();
    const parts: BlobPart[] = [];
    let got = 0;
    onProgress(total ? 0 : null);
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      parts.push(value);
      got += value.length;
      onProgress(total ? got / total : null);
    }
    blob = new Blob(parts, { type: res.headers.get("Content-Type") ?? "application/octet-stream" });
  } else {
    blob = await res.blob();
  }
  if (blob.size === 0) {
    throw new ApiError({ code: "download_failed", message: "Download failed: the file was empty.", retryable: true });
  }
  const match = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "");
  saveBlob(blob, match?.[1] ?? fallbackName);
}

export const downloadResult = (jobId: string, format: ExportFormat, quality: number, name: string, onProgress?: Progress) =>
  download(`/api/jobs/${jobId}/result?format=${format}&quality=${quality}&download=true`, undefined,
           `${name.replace(/\.[^.]+$/, "")}_enhanced.${format}`, onProgress);

export const downloadZip = (jobIds: string[], format: ExportFormat, quality: number, onProgress?: Progress) =>
  download("/api/download/zip", json({ job_ids: jobIds, format, quality }), "enhanced_images.zip", onProgress);
