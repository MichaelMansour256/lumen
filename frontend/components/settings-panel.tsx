"use client";

import {
  AlertTriangle, Brush, Camera, History, Moon, Mountain, Package, RotateCcw, Smile, Sparkles, User,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Enhancer } from "@/hooks/use-enhancer";

import { ActionBar } from "./action-bar";
import { Section, SliderField, ToggleRow } from "./settings/fields";
import { UpscaleSection } from "./settings/upscale-section";

const PRESET_ICONS: Record<string, LucideIcon> = {
  photo: Camera, portrait: User, product: Package, landscape: Mountain, illustration: Brush,
  anime: Smile, old_photo: History, low_light: Moon,
};
const SEVERITY_TONE = { low: "neutral", medium: "warning", high: "danger" } as const;

export function SettingsPanel({ e }: { e: Enhancer }) {
  const { shown, settings, update, system, selected } = e;
  const upscalers = system?.models.filter((m) => m.kind === "upscaler") ?? [];
  const faceModels = system?.models.filter((m) => m.kind === "face") ?? [];
  const faceModel = faceModels.find((m) => m.id === shown.face_model);
  const effectiveModel = settings.model === "auto" ? e.plan?.model ?? null : settings.model;
  const currentModel = upscalers.find((m) => m.id === effectiveModel);
  const noModels = system !== null && !upscalers.some((m) => m.available);
  const analysis = selected?.image.analysis ?? null;
  const rec = selected?.image.recommendation ?? null;
  const modelDenoises = effectiveModel === "realesr-general";

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border bg-background shadow-soft">
      <Tabs defaultValue="enhance" className="flex min-h-0 flex-1 flex-col">
        <div className="border-b px-5 py-3">
          <TabsList>
            <TabsTrigger value="enhance">Enhance</TabsTrigger>
            <TabsTrigger value="adjust">Adjust</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="enhance" className="thin-scroll min-h-0 flex-1 overflow-y-auto outline-none">
          {noModels && (
            <div role="alert" className="m-4 mb-0 flex gap-2 rounded-xl bg-warning/10 p-3 text-xs leading-snug text-warning">
              <AlertTriangle className="mt-px size-4 shrink-0" />
              <span>No AI models are available yet. Run <b>setup.bat</b> to install PyTorch and download the models. Only the non-AI Lanczos resize works until then.</span>
            </div>
          )}

          <Section
            title="Auto enhance"
            hint="Analyses each image and picks the model and corrections."
            action={<Switch aria-label="Auto enhance" checked={settings.auto} onChange={(auto) => update({ auto })} />}
          >
            {analysis ? (
              <div className="space-y-2 rounded-xl bg-surface p-3">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge tone="accent"><Sparkles className="size-3" />{analysis.category_label}</Badge>
                  {analysis.faces !== null && analysis.faces > 0 && <Badge>{analysis.faces} face{analysis.faces > 1 ? "s" : ""}</Badge>}
                  {analysis.grayscale && <Badge>Black &amp; white</Badge>}
                  {analysis.issues.map((issue) => (
                    <Badge key={issue.id + issue.label} tone={SEVERITY_TONE[issue.severity]}>{issue.label}</Badge>
                  ))}
                  {analysis.issues.length === 0 && <Badge tone="success">No quality problems measured</Badge>}
                </div>
                {settings.auto && rec && (
                  <ul className="space-y-1 text-xs leading-snug text-muted-foreground">
                    {rec.reasons.map((reason) => <li key={reason}>• {reason}</li>)}
                  </ul>
                )}
                {analysis.faces === null && <p className="text-[11px] text-muted-foreground">{analysis.faces_note}</p>}
                <p className="text-[11px] text-muted-foreground">{analysis.category_note}</p>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">Add an image to see its analysis.</p>
            )}
          </Section>

          <Section title="Mode" hint="Manual presets. Choosing one turns Auto off.">
            <div className="grid grid-cols-4 gap-1.5">
              {(system?.presets ?? []).map((preset) => {
                const Icon = PRESET_ICONS[preset.id] ?? Sparkles;
                return (
                  <button
                    key={preset.id}
                    type="button"
                    title={preset.description}
                    onClick={() => e.applyPreset(preset.id)}
                    className="flex flex-col items-center gap-1 rounded-xl border bg-background px-1 py-2 text-[11px] font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:bg-accent/50 hover:text-accent-foreground"
                  >
                    <Icon className="size-4" />
                    {preset.label}
                  </button>
                );
              })}
            </div>
          </Section>

          <UpscaleSection e={e} />

          <Section title="AI model">
            <Select aria-label="Upscaling model" value={settings.model} onChange={(ev) => update({ model: ev.target.value })}>
              <option value="auto">Automatic (based on analysis)</option>
              {upscalers.map((m) => (
                <option key={m.id} value={m.id} disabled={!m.available}>
                  {m.name}{m.available ? "" : " - not installed"}
                </option>
              ))}
              <option value="lanczos">Lanczos resize (no AI)</option>
            </Select>
            <p className="text-xs leading-snug text-muted-foreground">
              {settings.model === "lanczos" ? "Classic interpolation only. No detail is generated."
                : settings.model === "auto"
                  ? (currentModel ? `Will use ${currentModel.name} for this image.` : "Picks the best installed model for each image.")
                  : currentModel ? `${currentModel.description} Licence: ${currentModel.license}.` : ""}
            </p>
          </Section>

          <Section title="Face restoration" action={<Switch aria-label="Face restoration" checked={shown.face_restore} onChange={(v) => update({ face_restore: v })} />}>
            {shown.face_restore && (
              <div className="space-y-3">
                <Select aria-label="Face model" value={shown.face_model} onChange={(ev) => update({ face_model: ev.target.value })}>
                  {faceModels.map((m) => (
                    <option key={m.id} value={m.id} disabled={!m.available}>{m.name}{m.available ? "" : " - not installed"}</option>
                  ))}
                </Select>
                <SliderField label="Strength" value={shown.face_strength} onChange={(v) => update({ face_strength: v })}
                             hint="Lower keeps more of the original face; higher restores more detail." />
                {system && !system.face_detection && <p className="text-xs text-warning">The face detector is not installed, so faces cannot be found.</p>}
                {faceModel && !faceModel.available && <p className="text-xs text-warning">{faceModel.unavailable_reason}</p>}
              </div>
            )}
          </Section>

          <Section title="Detail and clean-up">
            <SliderField label="Noise reduction" value={shown.denoise} onChange={(v) => update({ denoise: v })}
                         hint={modelDenoises ? "Blends the model's weak and strong denoising weights." : "Non-local-means denoising before upscaling."} />
            <SliderField label="JPEG artifact removal" value={shown.jpeg_artifacts} onChange={(v) => update({ jpeg_artifacts: v })} />
            <SliderField label="Deblur" value={shown.deblur} onChange={(v) => update({ deblur: v })} hint="For mild focus blur." />
            <SliderField label="Texture detail" value={shown.detail} onChange={(v) => update({ detail: v })} />
            <SliderField label="Sharpness" value={shown.sharpness} onChange={(v) => update({ sharpness: v })} />
          </Section>
        </TabsContent>

        <TabsContent value="adjust" className="thin-scroll min-h-0 flex-1 overflow-y-auto outline-none">
          <Section title="Colour correction">
            <ToggleRow label="Auto colour" hint="White balance and levels." checked={shown.auto_color} onChange={(v) => update({ auto_color: v })} />
            <ToggleRow label="Restore faded colours" hint="Per-channel stretch for old, faded photos." checked={shown.fade_restore} onChange={(v) => update({ fade_restore: v })} />
            <SliderField label="Low-light enhancement" value={shown.low_light} onChange={(v) => update({ low_light: v })} />
          </Section>
          <Section
            title="Light and colour"
            action={<Button variant="ghost" size="sm" onClick={e.resetAdjustments}><RotateCcw />Reset</Button>}
          >
            <SliderField signed label="Exposure" value={settings.exposure} onChange={(v) => update({ exposure: v })} />
            <SliderField signed label="Brightness" value={settings.brightness} onChange={(v) => update({ brightness: v })} />
            <SliderField signed label="Contrast" value={settings.contrast} onChange={(v) => update({ contrast: v })} />
            <SliderField signed label="Saturation" value={settings.saturation} onChange={(v) => update({ saturation: v })} />
            <SliderField signed label="Colour temperature" value={settings.temperature} onChange={(v) => update({ temperature: v })} hint="Negative is cooler, positive is warmer." />
          </Section>
          <Section title="Enhancement intensity" hint="Blends the enhanced result with a plain resize of the original.">
            <IntensityField value={settings.intensity} onChange={(v) => update({ intensity: v })} />
          </Section>
        </TabsContent>
      </Tabs>
      <ActionBar e={e} />
    </div>
  );
}

function IntensityField({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between text-[13px]">
        <span>Intensity</span>
        <span className="text-xs tabular-nums text-muted-foreground">{Math.round(value * 100)}%</span>
      </div>
      <Slider aria-label="Enhancement intensity" value={value} onChange={onChange} />
    </div>
  );
}
