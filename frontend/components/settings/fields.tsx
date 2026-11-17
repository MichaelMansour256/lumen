"use client";

import { useEffect, useState, type ReactNode } from "react";

import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

export function Section({ title, hint, action, children, className }: {
  title: string; hint?: string; action?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={cn("space-y-3 border-b px-5 py-4 last:border-b-0", className)}>
      <div className="flex items-center justify-between gap-2">
        <div>
          <h3 className="text-[13px] font-semibold tracking-tight text-foreground">{title}</h3>
          {hint && <p className="mt-0.5 text-xs leading-snug text-muted-foreground">{hint}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function SliderField({ label, value, onChange, signed, disabled, hint }: {
  label: string; value: number; onChange: (v: number) => void; signed?: boolean; disabled?: boolean; hint?: string;
}) {
  const shown = Math.round(value * 100);
  const changed = Math.abs(value) > 0.004;
  return (
    <div className={cn("space-y-1.5", disabled && "opacity-50")}>
      <div className="flex items-baseline justify-between">
        <label className="text-[13px] text-foreground">{label}</label>
        <button
          type="button"
          disabled={disabled || !changed}
          onClick={() => onChange(0)}
          title={changed ? "Reset" : undefined}
          className={cn("rounded px-1 text-xs tabular-nums", changed ? "font-medium text-accent-foreground hover:bg-accent" : "text-muted-foreground")}
        >
          {signed && shown > 0 ? `+${shown}` : shown}
        </button>
      </div>
      <Slider aria-label={label} value={value} min={signed ? -1 : 0} max={1} step={0.01} disabled={disabled} onChange={onChange} />
      {hint && <p className="text-[11px] leading-snug text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function ToggleRow({ label, hint, checked, onChange, disabled }: {
  label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className={cn(disabled && "opacity-50")}>
        <p className="text-[13px] text-foreground">{label}</p>
        {hint && <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{hint}</p>}
      </div>
      <Switch aria-label={label} checked={checked} onChange={onChange} disabled={disabled} />
    </div>
  );
}

/** Number box that lets the user type freely and commits valid values. */
export function NumberInput({ value, onCommit, min, max, suffix, placeholder, ariaLabel }: {
  value: number | null; onCommit: (v: number) => void; min: number; max: number;
  suffix?: string; placeholder?: string; ariaLabel: string;
}) {
  const [text, setText] = useState(value === null ? "" : String(value));
  const [focused, setFocused] = useState(false);
  useEffect(() => {
    if (!focused) setText(value === null ? "" : String(value));
  }, [value, focused]);
  const parsed = Number(text);
  const invalid = text !== "" && (!Number.isFinite(parsed) || parsed < min || parsed > max);
  return (
    <div className={cn("flex h-9 items-center rounded-lg border bg-background px-2.5 focus-within:ring-2 focus-within:ring-ring", invalid && "border-destructive")}>
      <input
        type="number"
        inputMode="numeric"
        aria-label={ariaLabel}
        aria-invalid={invalid}
        value={text}
        min={min}
        max={max}
        placeholder={placeholder}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onChange={(event) => {
          setText(event.target.value);
          const next = Number(event.target.value);
          if (event.target.value !== "" && Number.isFinite(next) && next >= min && next <= max) onCommit(Math.round(next));
        }}
        className="w-full min-w-0 bg-transparent text-sm tabular-nums outline-none ring-0 focus-visible:ring-0 focus-visible:ring-offset-0"
      />
      {suffix && <span className="pl-1 text-xs text-muted-foreground">{suffix}</span>}
    </div>
  );
}
