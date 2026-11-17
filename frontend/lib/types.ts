export type ScaleMode = "factor" | "percent" | "dimensions";
export type ExportFormat = "png" | "jpg" | "webp";
export type JobStatus = "queued" | "processing" | "completed" | "failed" | "cancelled";

export interface EnhanceSettings {
  auto: boolean;
  scale_mode: ScaleMode;
  factor: number;
  percent: number;
  width: number | null;
  height: number | null;
  model: string;
  face_restore: boolean;
  face_model: string;
  face_strength: number;
  denoise: number;
  jpeg_artifacts: number;
  deblur: number;
  detail: number;
  sharpness: number;
  auto_color: boolean;
  fade_restore: boolean;
  low_light: number;
  exposure: number;
  brightness: number;
  contrast: number;
  saturation: number;
  temperature: number;
  intensity: number;
  device: "auto" | "cpu";
}

export interface ApiErrorBody {
  code: string;
  message: string;
  retryable: boolean;
  details: {
    suggested_factor?: number | null;
    suggested?: { width: number; height: number } | null;
    max_factor?: number;
  };
}

export interface AnalysisIssue {
  id: string;
  label: string;
  severity: "low" | "medium" | "high";
}

export interface Analysis {
  width: number;
  height: number;
  category: string;
  category_label: string;
  category_note: string;
  grayscale: boolean;
  faces: number | null;
  faces_note: string | null;
  issues: AnalysisIssue[];
  metrics: Record<string, number>;
}

export interface Recommendation {
  settings: Partial<EnhanceSettings>;
  reasons: string[];
  model_available: boolean;
}

export interface ImageRecord {
  id: string;
  name: string;
  format: string;
  width: number;
  height: number;
  size_bytes: number;
  has_alpha: boolean;
  analysis: Analysis | null;
  recommendation: Recommendation | null;
  url: string;
  upload_index?: number;
}

export interface JobResult {
  width: number;
  height: number;
  size_bytes: number;
  model: string;
  passes: number;
  device: string;
  fp16: boolean;
  tile: number;
  faces_restored: number;
  warnings: string[];
  notes: string[];
  seconds: number;
}

export interface Job {
  id: string;
  image_id: string;
  status: JobStatus;
  progress: number;
  stage: string;
  error: ApiErrorBody | null;
  result: JobResult | null;
  attempts: number;
  queue_position: number | null;
  result_url: string | null;
}

export interface ModelInfo {
  id: string;
  name: string;
  kind: "upscaler" | "face";
  scale: number;
  description: string;
  license: string;
  notes: string;
  installed: boolean;
  available: boolean;
  unavailable_reason: string | null;
}

export interface DeviceInfo {
  torch_available: boolean;
  torch_version: string | null;
  cuda_available: boolean;
  device: "cuda" | "cpu";
  gpu_name: string | null;
  vram_total_mb: number | null;
  vram_free_mb: number | null;
  fp16: boolean;
  note: string | null;
}

export interface Preset {
  id: string;
  label: string;
  description: string;
  settings: Partial<EnhanceSettings>;
}

export interface SystemInfo {
  device: DeviceInfo;
  models: ModelInfo[];
  face_detection: boolean;
  presets: Preset[];
  public?: boolean;
  defaults: EnhanceSettings;
  limits: {
    max_upload_mb: number;
    max_files_per_upload: number;
    max_input_pixels: number;
    max_output_pixels: number;
    max_output_side: number;
    max_factor: number;
    file_ttl_hours: number;
  };
}

export interface Plan {
  src_w: number;
  src_h: number;
  out_w: number;
  out_h: number;
  factor: number;
  passes: number;
  megapixels: number;
  est_memory_mb: number;
  est_file_bytes: number;
  model: string | null;
  notes: string[];
  blocked: string | null;
}

export interface QueueItem {
  image: ImageRecord;
  thumb: string;
  job: Job | null;
}

export interface Notice {
  id: number;
  kind: "error" | "info";
  text: string;
}
