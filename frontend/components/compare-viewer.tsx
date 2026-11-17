"use client";

import { ChevronsLeftRight, Maximize, Minimize, Minus, Plus, Scan } from "lucide-react";
import {
  useCallback, useEffect, useLayoutEffect, useRef, useState,
  type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent, type ReactNode,
} from "react";

import { Button } from "@/components/ui/button";
import { clamp, cn } from "@/lib/utils";

interface CompareViewerProps {
  beforeUrl: string;
  afterUrl: string | null;
  /** Pixel size of the image the stage represents (the output when there is one). */
  width: number;
  height: number;
  overlay?: ReactNode;
}

interface View { scale: number; x: number; y: number }

const MAX_PIXEL_ZOOM = 8;       // one image pixel may cover at most 8 screen pixels
const PADDING = 24;

/**
 * Before/after comparison. Both images are stretched into the same stage box,
 * so they stay pixel-aligned at every zoom level; the "after" image is clipped
 * at the divider. Wheel zooms around the cursor, dragging pans.
 */
export function CompareViewer({ beforeUrl, afterUrl, width, height, overlay }: CompareViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState({ w: 0, h: 0 });
  const [view, setView] = useState<View>({ scale: 1, x: 0, y: 0 });
  const [split, setSplit] = useState(0.5);
  const [fullscreen, setFullscreen] = useState(false);
  const [afterReady, setAfterReady] = useState(false);
  const drag = useRef<{ kind: "pan" | "split"; px: number; py: number; x: number; y: number } | null>(null);

  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () => setBox({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Stage size at "fit" zoom.
  const availW = Math.max(1, box.w - PADDING * 2);
  const availH = Math.max(1, box.h - PADDING * 2);
  const fit = Math.min(availW / width, availH / height);
  const fitW = width * fit;
  const fitH = height * fit;
  const maxScale = Math.max(1, MAX_PIXEL_ZOOM / fit);

  const constrain = useCallback((v: View): View => {
    const scale = clamp(v.scale, 1, maxScale);
    const w = fitW * scale;
    const h = fitH * scale;
    // Centre when smaller than the viewport, otherwise keep the viewport covered.
    const x = w <= box.w ? (box.w - w) / 2 : clamp(v.x, box.w - w - PADDING, PADDING);
    const y = h <= box.h ? (box.h - h) / 2 : clamp(v.y, box.h - h - PADDING, PADDING);
    return { scale, x, y };
  }, [box.w, box.h, fitW, fitH, maxScale]);

  const zoomAt = useCallback((factor: number, cx?: number, cy?: number) => {
    setView((prev) => {
      const px = cx ?? box.w / 2;
      const py = cy ?? box.h / 2;
      const scale = clamp(prev.scale * factor, 1, maxScale);
      const k = scale / prev.scale;
      return constrain({ scale, x: px - (px - prev.x) * k, y: py - (py - prev.y) * k });
    });
  }, [box.w, box.h, maxScale, constrain]);

  const fitToScreen = useCallback(() => setView(constrain({ scale: 1, x: 0, y: 0 })), [constrain]);
  const actualSize = useCallback(() => {
    const scale = clamp(1 / fit, 1, maxScale);
    setView(constrain({ scale, x: (box.w - fitW * scale) / 2, y: (box.h - fitH * scale) / 2 }));
  }, [fit, maxScale, constrain, box.w, box.h, fitW, fitH]);

  // Re-fit when the image or the viewport changes.
  useEffect(() => { fitToScreen(); }, [beforeUrl, width, height, box.w, box.h]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setAfterReady(false); setSplit(0.5); }, [afterUrl]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = el.getBoundingClientRect();
      zoomAt(Math.exp(-event.deltaY * 0.0016), event.clientX - rect.left, event.clientY - rect.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  useEffect(() => {
    const onChange = () => setFullscreen(document.fullscreenElement === containerRef.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void containerRef.current?.requestFullscreen?.();
  };

  const onPointerDown = (kind: "pan" | "split") => (event: ReactPointerEvent<HTMLElement>) => {
    if (event.button !== 0) return;
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { kind, px: event.clientX, py: event.clientY, x: view.x, y: view.y };
  };
  const onPointerMove = (event: ReactPointerEvent<HTMLElement>) => {
    const d = drag.current;
    if (!d) return;
    if (d.kind === "split") {
      const rect = containerRef.current!.getBoundingClientRect();
      setSplit(clamp((event.clientX - rect.left) / rect.width, 0, 1));
    } else {
      setView((prev) => constrain({ scale: prev.scale, x: d.x + event.clientX - d.px, y: d.y + event.clientY - d.py }));
    }
  };
  const onPointerUp = () => { drag.current = null; };

  const onSplitKey = (event: ReactKeyboardEvent) => {
    if (event.key === "ArrowLeft") setSplit((s) => clamp(s - 0.02, 0, 1));
    if (event.key === "ArrowRight") setSplit((s) => clamp(s + 0.02, 0, 1));
  };

  const comparing = Boolean(afterUrl && afterReady);
  // Divider position in stage-local pixels (before the CSS scale is applied).
  const clipLeft = clamp((split * box.w - view.x) / view.scale, 0, fitW);
  const pixelZoom = fit * view.scale;                     // screen px per image px
  const rendering = pixelZoom >= 3 ? "pixelated" : "auto";
  const imgClass = "absolute inset-0 size-full max-w-none select-none";

  return (
    <div
      ref={containerRef}
      className={cn("checker relative size-full touch-none overflow-hidden", fullscreen ? "rounded-none" : "rounded-2xl",
                    view.scale > 1 ? "cursor-grab active:cursor-grabbing" : "cursor-default")}
      onPointerDown={onPointerDown("pan")}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onDoubleClick={(ev) => {
        if (view.scale > 1) { fitToScreen(); return; }
        // Zoom to 100% around the point that was double-clicked.
        const rect = containerRef.current!.getBoundingClientRect();
        zoomAt(clamp(1 / fit, 1, maxScale), ev.clientX - rect.left, ev.clientY - rect.top);
      }}
    >
      {box.w > 0 && (
        <div
          className="absolute left-0 top-0 origin-top-left shadow-lift"
          style={{ width: fitW, height: fitH, transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={beforeUrl} alt="Original" draggable={false} className={imgClass} style={{ imageRendering: rendering }} />
          {afterUrl && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={afterUrl}
              alt="Enhanced"
              draggable={false}
              onLoad={() => setAfterReady(true)}
              className={cn(imgClass, !afterReady && "opacity-0")}
              style={{ imageRendering: rendering, clipPath: `inset(0px 0px 0px ${clipLeft}px)` }}
            />
          )}
        </div>
      )}

      {comparing && (
        <>
          <span className="pointer-events-none absolute left-3 top-3 rounded-full bg-foreground/75 px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-background backdrop-blur">Before</span>
          <span className="pointer-events-none absolute right-3 top-3 rounded-full bg-primary/90 px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-primary-foreground backdrop-blur">After</span>
          <div
            role="slider"
            tabIndex={0}
            aria-label="Before and after divider"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(split * 100)}
            className="group absolute inset-y-0 z-10 -ml-4 flex w-8 cursor-ew-resize justify-center"
            style={{ left: `${split * 100}%` }}
            onPointerDown={onPointerDown("split")}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            onKeyDown={onSplitKey}
            onDoubleClick={(e) => e.stopPropagation()}
          >
            <div className="h-full w-0.5 bg-background shadow-[0_0_0_1px_rgba(16,24,40,.25)]" />
            <div className="absolute top-1/2 flex size-9 -translate-y-1/2 items-center justify-center rounded-full bg-background text-foreground shadow-lift transition-transform group-hover:scale-110">
              <ChevronsLeftRight className="size-4" />
            </div>
          </div>
        </>
      )}
      {comparing && pixelZoom < 0.5 && (
        <span className="pointer-events-none absolute bottom-16 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap rounded-full bg-foreground/75 px-3 py-1 text-[11px] text-background backdrop-blur">
          Shown at {Math.round(pixelZoom * 100)}% - double-click a face to compare real detail
        </span>
      )}
      {!comparing && !overlay && (
        <span className="pointer-events-none absolute left-3 top-3 rounded-full bg-foreground/75 px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-background">Original</span>
      )}

      {overlay}

      <div
        className="absolute bottom-3 left-1/2 z-20 flex -translate-x-1/2 items-center gap-0.5 rounded-xl border bg-background/95 p-1 shadow-soft backdrop-blur"
        onPointerDown={(e) => e.stopPropagation()}
        onDoubleClick={(e) => e.stopPropagation()}
      >
        <Button variant="ghost" size="icon" aria-label="Zoom out" onClick={() => zoomAt(1 / 1.4)} disabled={view.scale <= 1.001}><Minus /></Button>
        <button
          type="button"
          onClick={actualSize}
          title="Show at 100% (actual pixels)"
          className="min-w-14 rounded-md px-1.5 py-1 text-center text-xs font-medium tabular-nums text-foreground hover:bg-muted"
        >
          {Math.round(pixelZoom * 100)}%
        </button>
        <Button variant="ghost" size="icon" aria-label="Zoom in" onClick={() => zoomAt(1.4)} disabled={view.scale >= maxScale - 0.001}><Plus /></Button>
        <span className="mx-1 h-5 w-px bg-border" />
        <Button variant="ghost" size="icon" aria-label="Fit to screen" title="Fit to screen" onClick={fitToScreen}><Scan /></Button>
        <Button variant="ghost" size="icon" aria-label={fullscreen ? "Exit fullscreen" : "Fullscreen"} title="Fullscreen" onClick={toggleFullscreen}>
          {fullscreen ? <Minimize /> : <Maximize />}
        </Button>
      </div>
    </div>
  );
}
