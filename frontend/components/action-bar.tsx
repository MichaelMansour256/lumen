"use client";

import { Archive, Download, Loader2, Sparkles } from "lucide-react";

function progressLabel(p: number) {
  return p < 0 ? "Downloading…" : `Downloading ${Math.round(p * 100)}%`;
}

import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import type { Enhancer } from "@/hooks/use-enhancer";
import type { ExportFormat } from "@/lib/types";

const isActive = (status?: string) => status === "queued" || status === "processing";

/** Enhance + download controls pinned to the bottom of the settings panel. */
export function ActionBar({ e }: { e: Enhancer }) {
  const { items, selected, completed, format, quality } = e;
  const busySelected = isActive(selected?.job?.status);
  const idle = items.filter((i) => !isActive(i.job?.status));
  const anyBusy = items.some((i) => isActive(i.job?.status));
  const blocked = Boolean(e.planError) || Boolean(e.plan?.blocked) || e.offline;
  const selectedDone = selected?.job?.status === "completed";

  return (
    <div className="space-y-3 border-t bg-background px-5 py-4">
      {e.plan?.blocked && <p role="alert" className="text-xs leading-snug text-warning">{e.plan.blocked}</p>}
      <div className="flex gap-2">
        <Button
          variant="primary"
          size="lg"
          className="flex-1"
          disabled={!selected || busySelected || blocked}
          onClick={() => selected && e.enhance([selected.image.id])}
        >
          {busySelected ? <Loader2 className="animate-spin" /> : <Sparkles />}
          {busySelected ? "Enhancing…" : selectedDone ? "Enhance again" : "Enhance"}
        </Button>
        {items.length > 1 && (
          <Button variant="dark" size="lg" disabled={!idle.length || e.offline} onClick={() => e.enhance(idle.map((i) => i.image.id))}
                  title="Apply the current settings to every image in the queue">
            {anyBusy && !idle.length ? <Loader2 className="animate-spin" /> : null}
            All ({items.length})
          </Button>
        )}
      </div>

      {completed.length > 0 && (
        <div className="space-y-2.5 rounded-xl bg-surface p-3">
          <div className="flex items-center gap-2">
            <div className="w-24 shrink-0">
              <Select aria-label="Download format" value={format} onChange={(ev) => e.setFormat(ev.target.value as ExportFormat)}>
                <option value="png">PNG</option>
                <option value="jpg">JPG</option>
                <option value="webp">WebP</option>
              </Select>
            </div>
            {format === "png" ? (
              <p className="text-xs text-muted-foreground">Lossless</p>
            ) : (
              <div className="flex flex-1 items-center gap-2">
                <Slider aria-label="Quality" value={quality} min={10} max={100} step={1} onChange={e.setQuality} />
                <span className="w-7 text-right text-xs tabular-nums text-muted-foreground">{quality}</span>
              </div>
            )}
          </div>
          {e.downloadProgress !== null ? (
            <div className="space-y-1.5" role="status">
              <p className="flex items-center gap-2 text-xs font-medium"><Loader2 className="size-3.5 animate-spin text-primary" />{progressLabel(e.downloadProgress)}</p>
              <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-primary transition-[width] duration-300"
                     style={{ width: e.downloadProgress < 0 ? "35%" : `${Math.round(e.downloadProgress * 100)}%` }} />
              </div>
            </div>
          ) : (
            <div className="flex gap-2">
              <Button className="flex-1" disabled={!selectedDone} onClick={() => selected && e.downloadOne(selected)}>
                <Download />Download
              </Button>
              {completed.length > 1 && (
                <Button className="flex-1" onClick={e.downloadAll}><Archive />ZIP ({completed.length})</Button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
