"use client";

import { AlertTriangle, ArrowRight, Lock, Unlock } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Enhancer } from "@/hooks/use-enhancer";
import { cn, formatBytes, formatDims, megapixels } from "@/lib/utils";

import { NumberInput, Section } from "./fields";

const FACTORS = [1, 2, 4, 8, 16];

export function UpscaleSection({ e }: { e: Enhancer }) {
  const { settings, update, selected, plan, planError, lockAspect, setLockAspect, setDimAnchor, format } = e;
  const image = selected?.image;
  const custom = settings.scale_mode !== "factor";
  const maxSide = e.system?.limits.max_output_side ?? 16384;

  const openCustom = () => {
    if (custom) return;
    const w = plan?.out_w ?? (image ? Math.round(image.width * settings.factor) : 1920);
    const h = plan?.out_h ?? (image ? Math.round(image.height * settings.factor) : 1080);
    update({ scale_mode: "dimensions", width: w, height: h, percent: Math.round(settings.factor * 100) });
  };
  const setWidth = (w: number) => {
    setDimAnchor("width");
    update({ width: w, ...(lockAspect && image ? { height: Math.max(1, Math.round((w * image.height) / image.width)) } : {}) });
  };
  const setHeight = (h: number) => {
    setDimAnchor("height");
    update({ height: h, ...(lockAspect && image ? { width: Math.max(1, Math.round((h * image.width) / image.height)) } : {}) });
  };
  const toggleLock = () => {
    const next = !lockAspect;
    setLockAspect(next);
    if (next && image && settings.width) setWidth(settings.width);
  };

  const suggestion = planError?.details.suggested_factor;
  return (
    <Section title="Upscale" hint="Output size. 1× enhances without changing the dimensions.">
      <div className="grid grid-cols-6 gap-1 rounded-lg bg-muted p-1">
        {FACTORS.map((f) => {
          const active = !custom && settings.factor === f;
          return (
            <button
              key={f}
              type="button"
              aria-pressed={active}
              onClick={() => update({ scale_mode: "factor", factor: f })}
              className={cn("h-8 rounded-md text-[13px] font-medium transition-colors",
                            active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}
            >
              {f}×
            </button>
          );
        })}
        <button
          type="button"
          aria-pressed={custom}
          onClick={openCustom}
          className={cn("h-8 rounded-md text-[13px] font-medium transition-colors",
                        custom ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}
        >
          Custom
        </button>
      </div>

      {custom && (
        <div className="space-y-2.5 rounded-xl border bg-surface/60 p-3">
          <div className="flex gap-1 text-xs">
            {(["dimensions", "percent"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => update({ scale_mode: mode })}
                className={cn("rounded-md px-2.5 py-1 font-medium capitalize",
                              settings.scale_mode === mode ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-muted")}
              >
                {mode === "dimensions" ? "Width × height" : "Percentage"}
              </button>
            ))}
          </div>
          {settings.scale_mode === "dimensions" ? (
            <div className="flex items-center gap-2">
              <div className="flex-1"><NumberInput ariaLabel="Output width" value={settings.width} onCommit={setWidth} min={8} max={maxSide} suffix="px" placeholder="Width" /></div>
              <Button
                variant={lockAspect ? "soft" : "ghost"}
                size="icon"
                aria-pressed={lockAspect}
                aria-label={lockAspect ? "Aspect ratio locked" : "Aspect ratio unlocked"}
                title={lockAspect ? "Aspect ratio locked" : "Aspect ratio unlocked"}
                onClick={toggleLock}
              >
                {lockAspect ? <Lock /> : <Unlock />}
              </Button>
              <div className="flex-1"><NumberInput ariaLabel="Output height" value={settings.height} onCommit={setHeight} min={8} max={maxSide} suffix="px" placeholder="Height" /></div>
            </div>
          ) : (
            <NumberInput ariaLabel="Scale percentage" value={Math.round(settings.percent)} onCommit={(p) => update({ percent: p })} min={10} max={1600} suffix="%" />
          )}
          {lockAspect && settings.scale_mode === "dimensions" && e.items.length > 1 && (
            <p className="text-[11px] leading-snug text-muted-foreground">In a batch, each image keeps its own aspect ratio.</p>
          )}
        </div>
      )}

      {image && plan && (
        <div className="rounded-xl bg-surface px-3 py-2.5 text-xs">
          <div className="flex items-center gap-1.5 font-medium tabular-nums text-foreground">
            <span className="text-muted-foreground">{formatDims(plan.src_w, plan.src_h)}</span>
            <ArrowRight className="size-3.5 text-muted-foreground" />
            <span>{formatDims(plan.out_w, plan.out_h)}</span>
          </div>
          <p className="mt-1 text-muted-foreground">
            {megapixels(plan.out_w, plan.out_h)} · approx. {formatBytes(plan.est_file_bytes)} as {format.toUpperCase()}
            {plan.passes > 1 ? ` · ${plan.passes} AI passes` : ""}
          </p>
        </div>
      )}
      {image && planError && (
        <div role="alert" className="space-y-2 rounded-xl bg-destructive/5 px-3 py-2.5 text-xs text-destructive">
          <p className="flex gap-1.5 leading-snug"><AlertTriangle className="mt-px size-3.5 shrink-0" />{planError.message}</p>
          {suggestion ? (
            <Button size="sm" variant="outline" onClick={() => update({ scale_mode: "factor", factor: suggestion })}>
              Use {suggestion}× instead
            </Button>
          ) : null}
        </div>
      )}
    </Section>
  );
}
