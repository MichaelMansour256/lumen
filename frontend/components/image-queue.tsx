"use client";

import { AlertTriangle, Check, Loader2, Plus, Trash2, X } from "lucide-react";
import { useRef } from "react";

import { Button } from "@/components/ui/button";
import type { Enhancer } from "@/hooks/use-enhancer";
import type { QueueItem } from "@/lib/types";
import { cn, formatBytes, formatDims } from "@/lib/utils";

import { ACCEPT } from "./dropzone";

function StatusIcon({ item }: { item: QueueItem }) {
  const status = item.job?.status;
  if (status === "queued" || status === "processing") return <Loader2 className="size-3.5 animate-spin text-primary" />;
  if (status === "completed") return <Check className="size-3.5 text-success" />;
  if (status === "failed") return <AlertTriangle className="size-3.5 text-destructive" />;
  return null;
}

function statusText(item: QueueItem): string {
  const job = item.job;
  if (!job) return `${formatDims(item.image.width, item.image.height)} · ${formatBytes(item.image.size_bytes)}`;
  if (job.status === "queued") return job.queue_position ? `Queued (#${job.queue_position})` : "Queued";
  if (job.status === "processing") return `${job.stage} ${Math.round(job.progress * 100)}%`;
  if (job.status === "completed" && job.result) return `Done · ${formatDims(job.result.width, job.result.height)}`;
  if (job.status === "failed") return "Failed";
  return "Cancelled";
}

export function ImageQueue({ e }: { e: Enhancer }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="flex items-stretch gap-2 rounded-2xl border bg-background p-2 shadow-soft">
      <div className="thin-scroll flex min-w-0 flex-1 gap-2 overflow-x-auto p-0.5">
        {e.items.map((item) => {
          const active = item.image.id === e.selectedId;
          const processing = item.job?.status === "processing";
          return (
            <div
              key={item.image.id}
              role="button"
              tabIndex={0}
              aria-pressed={active}
              onClick={() => e.setSelectedId(item.image.id)}
              onKeyDown={(ev) => { if (ev.key === "Enter") e.setSelectedId(item.image.id); }}
              className={cn("group relative flex w-52 shrink-0 cursor-pointer items-center gap-2.5 overflow-hidden rounded-xl border p-1.5 pr-2 text-left transition-colors",
                            active ? "border-primary/60 bg-accent/60" : "bg-background hover:bg-muted/50")}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {item.thumb
                ? <img src={item.thumb} alt="" loading="lazy" className="size-11 shrink-0 rounded-lg bg-muted object-cover" />
                : <span className="size-11 shrink-0 animate-pulse rounded-lg bg-muted" />}
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium text-foreground" title={item.image.name}>{item.image.name}</p>
                <p className="flex items-center gap-1 truncate text-[11px] text-muted-foreground"><StatusIcon item={item} />{statusText(item)}</p>
              </div>
              <button
                type="button"
                aria-label={`Remove ${item.image.name}`}
                onClick={(ev) => { ev.stopPropagation(); e.removeItem(item.image.id); }}
                className="rounded-md p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-muted hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100"
              >
                <X className="size-3.5" />
              </button>
              {processing && (
                <span className="absolute inset-x-0 bottom-0 h-0.5 bg-muted">
                  <span className="block h-full bg-primary transition-[width] duration-300" style={{ width: `${Math.round((item.job?.progress ?? 0) * 100)}%` }} />
                </span>
              )}
            </div>
          );
        })}
      </div>
      <div className="flex shrink-0 flex-col justify-center gap-1">
        <Button size="sm" onClick={() => input.current?.click()} disabled={e.uploading}>
          {e.uploading ? <Loader2 className="animate-spin" /> : <Plus />}Add
        </Button>
        <Button size="sm" variant="danger" onClick={e.clearAll}><Trash2 />Clear</Button>
      </div>
      <input ref={input} type="file" accept={ACCEPT} multiple hidden
             onChange={(ev) => { if (ev.target.files?.length) void e.addFiles(ev.target.files); ev.target.value = ""; }} />
    </div>
  );
}
