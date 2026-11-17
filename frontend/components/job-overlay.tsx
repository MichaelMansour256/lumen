"use client";

import { AlertTriangle, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Enhancer } from "@/hooks/use-enhancer";
import type { Job } from "@/lib/types";

/** Progress / error card shown over the viewer for the selected image's job. */
export function JobOverlay({ job, e }: { job: Job; e: Enhancer }) {
  if (job.status === "queued" || job.status === "processing") {
    const pct = Math.round(job.progress * 100);
    return (
      <div className="absolute inset-x-0 top-4 z-20 mx-auto w-[min(92%,22rem)] rounded-2xl border bg-background/95 p-4 shadow-lift backdrop-blur" onPointerDown={(ev) => ev.stopPropagation()}>
        <div className="flex items-center gap-2 text-sm font-medium">
          <Loader2 className="size-4 animate-spin text-primary" />
          <span className="flex-1 truncate">{job.status === "queued" ? (job.queue_position ? `Queued (#${job.queue_position})` : "Queued") : job.stage || "Processing"}</span>
          <span className="tabular-nums text-muted-foreground">{job.status === "processing" ? `${pct}%` : ""}</span>
        </div>
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
          <div className="h-full rounded-full bg-primary transition-[width] duration-300" style={{ width: `${pct}%` }} />
        </div>
        <div className="mt-3 flex justify-end">
          <Button size="sm" variant="ghost" onClick={() => e.cancel(job.id)}>Cancel</Button>
        </div>
      </div>
    );
  }
  if (job.status === "failed" || job.status === "cancelled") {
    const failed = job.status === "failed";
    const suggestion = job.error?.details?.suggested_factor;
    return (
      <div role="alert" className="absolute inset-x-0 top-4 z-20 mx-auto w-[min(92%,26rem)] rounded-2xl border bg-background/95 p-4 shadow-lift backdrop-blur" onPointerDown={(ev) => ev.stopPropagation()}>
        <p className="flex items-center gap-2 text-sm font-semibold">
          <AlertTriangle className={failed ? "size-4 text-destructive" : "size-4 text-muted-foreground"} />
          {failed ? "Processing failed" : "Processing cancelled"}
        </p>
        {failed && <p className="mt-1.5 text-[13px] leading-snug text-muted-foreground">{job.error?.message ?? "Unknown error."}</p>}
        <div className="mt-3 flex flex-wrap justify-end gap-2">
          {failed && job.error?.code === "gpu_oom" && (
            <Button size="sm" onClick={() => e.retry(job.id, "cpu")}>Retry on CPU (slow)</Button>
          )}
          {suggestion ? (
            <Button size="sm" onClick={() => e.update({ scale_mode: "factor", factor: suggestion })}>Switch to {suggestion}×</Button>
          ) : null}
          <Button size="sm" variant="primary" onClick={() => e.retry(job.id)}>Retry</Button>
        </div>
      </div>
    );
  }
  return null;
}
