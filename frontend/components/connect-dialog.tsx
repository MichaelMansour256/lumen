"use client";

import { KeyRound, Loader2, Server, X } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import type { Enhancer } from "@/hooks/use-enhancer";
import { DEFAULT_API_URL, normaliseUrl } from "@/lib/api";

/** Server address + access key. Opened automatically when the server asks for a key. */
export function ConnectDialog({ e, open, onClose }: { e: Enhancer; open: boolean; onClose: () => void }) {
  const [url, setUrl] = useState(e.connection.url);
  const [key, setKey] = useState(e.connection.key);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) { setUrl(e.connection.url); setKey(e.connection.key); }
  }, [open, e.connection]);

  useEffect(() => {
    if (!open) return;
    const onKey = (ev: KeyboardEvent) => { if (ev.key === "Escape" && !e.needsAuth && !e.needsLink) onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, e.needsAuth, e.needsLink]);

  if (!open) return null;

  const submit = async (ev: FormEvent) => {
    ev.preventDefault();
    setBusy(true);
    try {
      await e.connect({ url: normaliseUrl(url) || DEFAULT_API_URL, key });
    } finally {
      setBusy(false);
    }
    onClose();
  };

  const field = "h-10 w-full rounded-lg border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring";
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-foreground/30 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="connect-title">
      <form onSubmit={submit} className="w-full max-w-md rounded-2xl border bg-background p-6 shadow-lift">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="connect-title" className="font-display text-lg font-semibold tracking-tight">Connect to a server</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {e.needsLink
                ? "This online page needs a server. On the PC running Lumen, start start_public.bat and open the share link it prints - or paste the server address and key here."
                : e.needsAuth ? "This server needs an access key. Open the share link you were given, or enter the details here."
                : "Images are processed on the computer running the Lumen backend."}
            </p>
          </div>
          {!e.needsAuth && !e.needsLink && (
            <Button variant="ghost" size="icon" aria-label="Close" onClick={onClose}><X /></Button>
          )}
        </div>
        <label className="mt-5 block text-[13px] font-medium" htmlFor="server-url">Server address</label>
        <div className="relative mt-1.5">
          <Server className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input id="server-url" className={`${field} pl-9`} value={url} onChange={(ev) => setUrl(ev.target.value)}
                 placeholder="https://example.trycloudflare.com" autoComplete="url" spellCheck={false} />
        </div>
        <label className="mt-4 block text-[13px] font-medium" htmlFor="access-key">Access key</label>
        <div className="relative mt-1.5">
          <KeyRound className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input id="access-key" type="password" className={`${field} pl-9`} value={key} onChange={(ev) => setKey(ev.target.value)}
                 placeholder="Leave empty for a local server" autoComplete="off" spellCheck={false} />
        </div>
        <div className="mt-6 flex justify-between gap-2">
          <Button variant="ghost" onClick={() => { setUrl(DEFAULT_API_URL); setKey(""); }}>Use local server</Button>
          <Button type="submit" variant="primary" disabled={busy}>{busy && <Loader2 className="animate-spin" />}Connect</Button>
        </div>
      </form>
    </div>
  );
}
