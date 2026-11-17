"use client";

import { Info, Loader2, Upload, X } from "lucide-react";
import { useEffect, useState } from "react";

import { CompareViewer } from "@/components/compare-viewer";
import { ConnectDialog } from "@/components/connect-dialog";
import { Dropzone } from "@/components/dropzone";
import { Header } from "@/components/header";
import { ImageQueue } from "@/components/image-queue";
import { JobOverlay } from "@/components/job-overlay";
import { SettingsPanel } from "@/components/settings-panel";
import { useAuthedImage } from "@/hooks/use-authed-image";
import { useEnhancer } from "@/hooks/use-enhancer";
import { isLocalServer, previewPath, resultPath } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn, formatBytes, formatDims } from "@/lib/utils";

export default function Page() {
  const e = useEnhancer();
  const { selected, addFiles } = e;
  const [dragging, setDragging] = useState(false);
  const [serverOpen, setServerOpen] = useState(false);
  const [afterTry, setAfterTry] = useState(0);

  // Drop anywhere on the page, or paste an image from the clipboard.
  useEffect(() => {
    let depth = 0;
    const hasFiles = (ev: DragEvent) => Array.from(ev.dataTransfer?.types ?? []).includes("Files");
    const onEnter = (ev: DragEvent) => { if (hasFiles(ev)) { depth += 1; setDragging(true); } };
    const onLeave = () => { depth = Math.max(0, depth - 1); if (depth === 0) setDragging(false); };
    const onOver = (ev: DragEvent) => { if (hasFiles(ev)) ev.preventDefault(); };
    const onDrop = (ev: DragEvent) => {
      if (!hasFiles(ev)) return;
      ev.preventDefault();
      depth = 0;
      setDragging(false);
      if (ev.dataTransfer?.files.length) void addFiles(ev.dataTransfer.files);
    };
    const onPaste = (ev: ClipboardEvent) => {
      const files = Array.from(ev.clipboardData?.items ?? [])
        .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
        .map((item, i) => {
          const file = item.getAsFile();
          if (!file) return null;
          const ext = file.type.split("/")[1] ?? "png";
          return file.name && file.name !== "image.png" ? file : new File([file], `pasted-${Date.now()}-${i + 1}.${ext}`, { type: file.type });
        })
        .filter((file): file is File => file !== null);
      if (files.length) { ev.preventDefault(); void addFiles(files); }
    };
    window.addEventListener("dragenter", onEnter);
    window.addEventListener("dragleave", onLeave);
    window.addEventListener("dragover", onOver);
    window.addEventListener("drop", onDrop);
    window.addEventListener("paste", onPaste);
    return () => {
      window.removeEventListener("dragenter", onEnter);
      window.removeEventListener("dragleave", onLeave);
      window.removeEventListener("dragover", onOver);
      window.removeEventListener("drop", onDrop);
      window.removeEventListener("paste", onPaste);
    };
  }, [addFiles]);

  const job = selected?.job ?? null;
  const result = job?.status === "completed" ? job.result : null;
  const local = e.ready ? isLocalServer() : true;
  // Over the internet the viewer uses a reduced WebP preview; the download is always full size.
  const afterPath = job && result ? `${local ? resultPath(job.id) : previewPath(job.id)}?v=${job.attempts}.${afterTry}` : null;
  const before = useAuthedImage(selected ? selected.image.url : null);
  const after = useAuthedImage(afterPath);
  const beforeUrl = before.url ?? (selected?.thumb || null);
  let serverLabel = "Local server · images stay on this computer";
  if (!local) {
    try { serverLabel = new URL(e.connection.url).host; } catch { serverLabel = e.connection.url; }
  }

  return (
    <div className="flex min-h-dvh flex-col lg:h-dvh">
      <Header system={e.system} offline={e.offline} needsAuth={e.needsAuth} needsLink={e.needsLink} serverLabel={serverLabel} onServerClick={() => setServerOpen(true)} />
      {e.offline && !e.needsLink && (
        <div role="alert" className="border-b bg-destructive/5 px-5 py-2 text-center text-xs text-destructive">
          {local
            ? <>Cannot reach the enhancement server at {e.connection.url.replace(/^https?:\/\//, "")}. Start it with <b>start.bat</b>; this page reconnects automatically.</>
            : <>Cannot reach the enhancement server at {serverLabel}. It may be switched off, or the link has changed.{" "}
                <button type="button" className="font-medium underline" onClick={() => setServerOpen(true)}>Change server</button></>}
        </div>
      )}

      <main className="grid min-h-0 flex-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_23.5rem]">
        <section className="flex min-w-0 flex-col gap-3 lg:min-h-0">
          <div className="relative h-[58vh] min-h-[320px] lg:h-auto lg:min-h-0 lg:flex-1">
            {selected && !beforeUrl ? (
              <div className="checker flex size-full items-center justify-center rounded-2xl text-sm text-muted-foreground">
                {before.error ?? <><Loader2 className="mr-2 size-4 animate-spin" />Loading image…</>}
              </div>
            ) : selected && beforeUrl ? (
              <CompareViewer
                key={selected.image.id}
                beforeUrl={beforeUrl}
                afterUrl={after.url}
                width={result?.width ?? selected.image.width}
                height={result?.height ?? selected.image.height}
                overlay={job && job.status !== "completed" ? <JobOverlay job={job} e={e} />
                  : afterPath && !after.url ? (
                    <div role="status" className="absolute inset-x-0 top-4 z-20 mx-auto flex w-fit max-w-[92%] items-center gap-2 rounded-xl border bg-background/95 px-4 py-2.5 text-[13px] shadow-lift"
                         onPointerDown={(ev) => ev.stopPropagation()}>
                      {after.error ? (
                        <>
                          <span className="text-destructive">Could not load the enhanced image: {after.error}</span>
                          <Button size="sm" onClick={() => setAfterTry((n) => n + 1)}>Retry</Button>
                        </>
                      ) : (
                        <><Loader2 className="size-4 animate-spin text-primary" />Loading enhanced image{local ? "" : " preview"}…</>
                      )}
                    </div>
                  ) : undefined}
              />
            ) : (
              <Dropzone onFiles={(files) => void addFiles(files)} uploading={e.uploading} maxMb={e.system?.limits.max_upload_mb ?? 50} local={local} />
            )}
          </div>

          {selected && (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-1 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">{selected.image.name}</span>
              <span>Original {formatDims(selected.image.width, selected.image.height)} · {formatBytes(selected.image.size_bytes)} · {selected.image.format.toUpperCase()}</span>
              {result && (
                <span className="text-foreground">
                  Enhanced {formatDims(result.width, result.height)} · {formatBytes(result.size_bytes)} PNG ·{" "}
                  {result.model === "lanczos" ? "Lanczos (no AI)" : e.system?.models.find((m) => m.id === result.model)?.name ?? result.model}
                  {result.model !== "lanczos" ? ` · ${result.device === "cuda" ? "GPU" : "CPU"}${result.fp16 ? " FP16" : ""}` : ""}
                  {result.faces_restored ? ` · ${result.faces_restored} face${result.faces_restored > 1 ? "s" : ""} restored` : ""} · {result.seconds}s
                </span>
              )}
              {result?.warnings.map((warning) => (
                <span key={warning} className="flex items-center gap-1 text-warning"><Info className="size-3.5" />{warning}</span>
              ))}
            </div>
          )}

          {e.items.length > 0 && <ImageQueue e={e} />}
        </section>

        <aside className="min-h-0 lg:h-full">
          <SettingsPanel e={e} />
        </aside>
      </main>

      <ConnectDialog e={e} open={serverOpen || e.needsAuth || e.needsLink} onClose={() => setServerOpen(false)} />

      {dragging && (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-primary/10 backdrop-blur-sm">
          <div className="flex items-center gap-3 rounded-2xl border-2 border-dashed border-primary bg-background px-8 py-6 text-base font-medium shadow-lift">
            <Upload className="size-5 text-primary" />Drop to add images
          </div>
        </div>
      )}

      <div className="fixed bottom-4 left-4 z-50 flex w-[min(92vw,24rem)] flex-col gap-2" aria-live="polite">
        {e.notices.map((notice) => (
          <div key={notice.id} role={notice.kind === "error" ? "alert" : "status"}
               className={cn("flex items-start gap-2 rounded-xl border bg-background p-3 text-[13px] leading-snug shadow-lift",
                             notice.kind === "error" ? "border-destructive/30" : "border-border")}>
            <span className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", notice.kind === "error" ? "bg-destructive" : "bg-primary")} />
            <span className="flex-1">{notice.text}</span>
            <button type="button" aria-label="Dismiss" onClick={() => e.dismissNotice(notice.id)} className="rounded p-0.5 text-muted-foreground hover:bg-muted">
              <X className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
