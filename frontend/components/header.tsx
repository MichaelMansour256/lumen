import { Cpu, KeyRound, Server, WifiOff, Zap } from "lucide-react";

import type { SystemInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

function Logo() {
  return (
    <svg viewBox="0 0 32 32" className="size-8" aria-hidden="true">
      <rect width="32" height="32" rx="9" fill="hsl(226 39% 13%)" />
      <path d="M9 21.5 14.2 12l3.6 6.2 2.2-3.4 3 6.7z" fill="#fff" opacity=".92" />
      <circle cx="21.6" cy="10.6" r="2.1" fill="hsl(243 85% 72%)" />
    </svg>
  );
}

export function Header({ system, offline, needsAuth, needsLink, serverLabel, onServerClick }: {
  system: SystemInfo | null; offline: boolean; needsAuth: boolean; needsLink?: boolean; serverLabel: string; onServerClick: () => void;
}) {
  const device = system?.device;
  let chip = { icon: Cpu, text: "Connecting…", tone: "text-muted-foreground bg-muted" };
  if (needsLink) chip = { icon: Server, text: "No server connected", tone: "text-warning bg-warning/10" };
  else if (needsAuth) chip = { icon: KeyRound, text: "Access key needed", tone: "text-warning bg-warning/10" };
  else if (offline) chip = { icon: WifiOff, text: "Backend offline", tone: "text-destructive bg-destructive/10" };
  else if (device?.device === "cuda") {
    const free = device.vram_free_mb ? ` · ${(device.vram_free_mb / 1024).toFixed(1)} GB free` : "";
    chip = { icon: Zap, text: `${(device.gpu_name ?? "GPU").replace(/^NVIDIA\s+/i, "")}${free}${device.fp16 ? " · FP16" : ""}`, tone: "text-success bg-success/10" };
  } else if (device) {
    chip = { icon: Cpu, text: device.torch_available ? "CPU mode (no CUDA GPU detected)" : "PyTorch not installed", tone: "text-warning bg-warning/10" };
  }
  const Icon = chip.icon;
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b bg-background px-4 sm:px-5">
      <div className="flex items-center gap-2.5">
        <Logo />
        <div className="leading-tight">
          <p className="font-display text-[15px] font-semibold tracking-tight">Lumen</p>
          <p className="hidden text-[11px] text-muted-foreground sm:block">AI image enhancer</p>
        </div>
      </div>
      <nav className="flex items-center gap-3">
        <button
          type="button"
          onClick={onServerClick}
          title="Change server"
          className="hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground md:inline-flex"
        >
          <Server className="size-3.5" />
          {serverLabel}
        </button>
        <span title={device?.note ?? undefined} className={cn("inline-flex max-w-[60vw] items-center gap-1.5 truncate rounded-full px-2.5 py-1 text-xs font-medium", chip.tone)}>
          <Icon className="size-3.5 shrink-0" />
          <span className="truncate">{chip.text}</span>
        </span>
      </nav>
    </header>
  );
}
