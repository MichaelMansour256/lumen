"use client";

import { ImagePlus, Loader2 } from "lucide-react";
import { useRef } from "react";

import { Button } from "@/components/ui/button";

export const ACCEPT = "image/jpeg,image/png,image/webp,image/tiff,.jpg,.jpeg,.png,.webp,.tif,.tiff";

export function Dropzone({ onFiles, uploading, maxMb, local }: { onFiles: (files: FileList) => void; uploading: boolean; maxMb: number; local: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div
      className="flex size-full flex-col items-center justify-center rounded-2xl border-2 border-dashed border-border bg-background px-6 text-center transition-colors hover:border-primary/40"
      onClick={() => input.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") input.current?.click(); }}
    >
      <div className="mb-5 flex size-14 items-center justify-center rounded-2xl bg-accent text-accent-foreground">
        {uploading ? <Loader2 className="size-6 animate-spin" /> : <ImagePlus className="size-6" />}
      </div>
      <h2 className="font-display text-xl font-semibold tracking-tight">Drop images to enhance</h2>
      <p className="mt-1.5 max-w-sm text-sm text-muted-foreground">
        Drag and drop, browse, or paste from the clipboard with Ctrl+V. Several images can be added at once.
      </p>
      <Button variant="primary" size="lg" className="mt-6" disabled={uploading} onClick={(ev) => { ev.stopPropagation(); input.current?.click(); }}>
        {uploading ? "Uploading…" : "Choose images"}
      </Button>
      <p className="mt-4 text-xs text-muted-foreground">JPG, PNG, WebP or TIFF · up to {maxMb} MB each · {local ? "processed on this computer only" : "processed on the connected server, deleted automatically"}</p>
      <input ref={input} type="file" accept={ACCEPT} multiple hidden
             onChange={(ev) => { if (ev.target.files?.length) onFiles(ev.target.files); ev.target.value = ""; }} />
    </div>
  );
}
