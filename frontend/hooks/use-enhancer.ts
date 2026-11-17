"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import * as api from "@/lib/api";
import type {
  EnhanceSettings, ExportFormat, Job, Notice, Plan, QueueItem, SystemInfo,
} from "@/lib/types";

/** Settings the automatic analysis chooses. Editing any of them switches to manual. */
export const AUTO_KEYS: (keyof EnhanceSettings)[] = [
  "face_restore", "face_strength", "denoise", "jpeg_artifacts", "deblur", "detail",
  "sharpness", "auto_color", "fade_restore", "low_light",
];

export const FALLBACK_DEFAULTS: EnhanceSettings = {
  auto: true, scale_mode: "factor", factor: 2, percent: 200, width: null, height: null,
  model: "auto", face_restore: false, face_model: "gfpgan", face_strength: 0.6, denoise: 0.25,
  jpeg_artifacts: 0, deblur: 0, detail: 0, sharpness: 0, auto_color: false, fade_restore: false,
  low_light: 0, exposure: 0, brightness: 0, contrast: 0, saturation: 0, temperature: 0,
  intensity: 1, device: "auto",
};

const BROWSER_PREVIEWABLE = ["image/jpeg", "image/png", "image/webp"];
const ACTIVE = ["queued", "processing"];
let noticeSeq = 0;

export function useEnhancer() {
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [offline, setOffline] = useState(false);
  const [items, setItems] = useState<QueueItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [settings, setSettings] = useState<EnhanceSettings>(FALLBACK_DEFAULTS);
  const [lockAspect, setLockAspect] = useState(true);
  const [dimAnchor, setDimAnchor] = useState<"width" | "height">("width");
  const [format, setFormat] = useState<ExportFormat>("png");
  const [quality, setQuality] = useState(90);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [planError, setPlanError] = useState<api.ApiError | null>(null);
  const [uploading, setUploading] = useState(false);
  /** null = idle; otherwise fraction 0..1, or -1 when the size is unknown. */
  const [downloadProgress, setDownloadProgress] = useState<number | null>(null);
  const onProgress = useCallback((f: number | null) => setDownloadProgress(f === null ? -1 : f), []);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [connection, setConnectionState] = useState<api.Connection>({ url: api.DEFAULT_API_URL, key: "" });
  const [ready, setReady] = useState(false);
  const [needsAuth, setNeedsAuth] = useState(false);
  /** Online copy of the site opened without a share link: nothing to connect to yet. */
  const [needsLink, setNeedsLink] = useState(false);
  const initialised = useRef(false);
  const itemsRef = useRef(items);
  itemsRef.current = items;

  const notify = useCallback((text: string, kind: Notice["kind"] = "error") => {
    const id = ++noticeSeq;
    setNotices((list) => [...list.slice(-3), { id, kind, text }]);
    setTimeout(() => setNotices((list) => list.filter((n) => n.id !== id)), 9000);
  }, []);
  const dismissNotice = useCallback((id: number) => setNotices((l) => l.filter((n) => n.id !== id)), []);

  /** Show an error; a rejected access key opens the connection dialog instead. */
  const fail = useCallback((err: unknown, fallback: string) => {
    if (err instanceof api.ApiError && err.code === "auth_required") {
      setNeedsAuth(true);
      return;
    }
    notify(err instanceof Error && err.message ? err.message : fallback);
  }, [notify]);

  // --- backend status (retries while offline) ---------------------------
  const refreshSystem = useCallback(async () => {
    try {
      const info = await api.getSystem();
      if (!initialised.current) {
        initialised.current = true;
        setSettings(info.defaults);
        if (info.public) setFormat("jpg");     // much smaller downloads over the internet
      }
      setSystem(info);
      setOffline(false);
      setNeedsAuth(false);
    } catch (err) {
      if (err instanceof api.ApiError && err.code === "auth_required") {
        setNeedsAuth(true);
        setOffline(false);
      } else {
        setOffline(true);
      }
    }
  }, []);

  useEffect(() => {
    setConnectionState(api.initConnection());
    setNeedsLink(api.isHostedRemotely() && api.isLocalServer());
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready || needsAuth || needsLink) return;
    void refreshSystem();
    const timer = setInterval(() => void refreshSystem(), offline ? 3000 : 20000);
    return () => clearInterval(timer);
  }, [ready, refreshSystem, offline, needsAuth, needsLink]);

  /** Switch server / access key. The image queue belongs to the old server, so it is cleared. */
  const connect = useCallback(async (next: api.Connection) => {
    const changedServer = api.normaliseUrl(next.url) !== api.getConnection().url;
    api.setConnection(next);
    setConnectionState(api.getConnection());
    if (changedServer) {
      itemsRef.current.forEach((i) => { if (i.thumb.startsWith("blob:")) URL.revokeObjectURL(i.thumb); });
      setItems([]);
      setSelectedId(null);
      setSystem(null);
    }
    setNeedsAuth(false);
    setNeedsLink(api.isHostedRemotely() && api.isLocalServer());
    await refreshSystem();
  }, [refreshSystem]);

  const selected = useMemo(
    () => items.find((i) => i.image.id === selectedId) ?? null, [items, selectedId]);

  /** What the controls display: in auto mode, the recommendation for the selected image. */
  const shown = useMemo<EnhanceSettings>(() => {
    const rec = selected?.image.recommendation;
    if (!settings.auto || !rec) return settings;
    return { ...settings, ...rec.settings, model: settings.model };
  }, [settings, selected]);

  /** The payload sent to the server (dimension lock resolved per image by the server). */
  const payload = useMemo<EnhanceSettings>(() => {
    if (settings.scale_mode !== "dimensions" || !lockAspect) return settings;
    return dimAnchor === "width" ? { ...settings, height: null } : { ...settings, width: null };
  }, [settings, lockAspect, dimAnchor]);

  const update = useCallback((patch: Partial<EnhanceSettings>) => {
    setSettings((prev) => {
      const touchesAuto = AUTO_KEYS.some((key) => key in patch);
      if (prev.auto && touchesAuto && patch.auto === undefined) {
        const current = itemsRef.current.find((i) => i.image.id === selectedId);
        const seed = current?.image.recommendation?.settings ?? {};
        // "model" stays whatever the user picked; other values start from what was displayed.
        return { ...prev, ...seed, model: prev.model, ...patch, auto: false };
      }
      return { ...prev, ...patch };
    });
  }, [selectedId]);

  const applyPreset = useCallback((presetId: string) => {
    const preset = system?.presets.find((p) => p.id === presetId);
    if (!preset) return;
    const base = system?.defaults ?? FALLBACK_DEFAULTS;
    setSettings((prev) => {
      const reset: Partial<EnhanceSettings> = {};
      AUTO_KEYS.forEach((key) => { (reset as Record<string, unknown>)[key] = base[key]; });
      return { ...prev, ...reset, model: "auto", saturation: 0, ...preset.settings, auto: false };
    });
  }, [system]);

  const resetAdjustments = useCallback(() => {
    setSettings((prev) => ({
      ...prev, exposure: 0, brightness: 0, contrast: 0, saturation: 0, temperature: 0,
      low_light: prev.auto ? prev.low_light : 0, intensity: 1,
    }));
  }, []);

  // --- uploads ------------------------------------------------------------
  const addFiles = useCallback(async (list: FileList | File[]) => {
    const files = Array.from(list);
    if (!files.length) return;
    const maxFiles = system?.limits.max_files_per_upload ?? 20;
    const maxMb = system?.limits.max_upload_mb ?? 50;
    const accepted: File[] = [];
    for (const file of files.slice(0, maxFiles)) {
      if (file.size > maxMb * 1024 * 1024) notify(`${file.name}: image too large (limit ${maxMb} MB).`);
      else accepted.push(file);
    }
    if (files.length > maxFiles) notify(`Only the first ${maxFiles} images were added.`, "info");
    if (!accepted.length) return;
    setUploading(true);
    try {
      const res = await api.uploadImages(accepted);
      res.errors.forEach((e) => notify(`${e.name}: ${e.error.message}`));
      const needThumbs: string[] = [];
      const added: QueueItem[] = res.images.map((image) => {
        const file = accepted[image.upload_index ?? -1];
        const local = file && BROWSER_PREVIEWABLE.includes(file.type);
        if (!local) needThumbs.push(image.id);
        return { image, thumb: local ? URL.createObjectURL(file) : "", job: null };
      });
      if (added.length) {
        setItems((prev) => [...prev, ...added]);
        setSelectedId((cur) => cur ?? added[0].image.id);
      }
      // TIFF and other formats the browser cannot show: use the server's PNG copy.
      needThumbs.forEach((id) => {
        api.fetchImageUrl(`/api/images/${id}/file`)
          .then((thumb) => setItems((prev) => prev.map((i) => (i.image.id === id ? { ...i, thumb } : i))))
          .catch(() => undefined);
      });
    } catch (err) {
      fail(err, "Upload failed.");
    } finally {
      setUploading(false);
    }
  }, [system, notify, fail]);

  const removeItem = useCallback((id: string) => {
    const item = itemsRef.current.find((i) => i.image.id === id);
    if (item?.thumb.startsWith("blob:")) URL.revokeObjectURL(item.thumb);
    const rest = itemsRef.current.filter((i) => i.image.id !== id);
    setItems(rest);
    setSelectedId((cur) => (cur === id ? rest[0]?.image.id ?? null : cur));
    api.deleteImage(id).catch(() => undefined);      // server also expires files on its own
  }, []);

  const clearAll = useCallback(() => {
    itemsRef.current.forEach((i) => removeItem(i.image.id));
  }, [removeItem]);

  // --- jobs -----------------------------------------------------------------
  const setJob = useCallback((job: Job) => {
    setItems((prev) => prev.map((i) => (i.image.id === job.image_id ? { ...i, job } : i)));
  }, []);

  const enhance = useCallback(async (ids: string[]) => {
    const targets = ids.filter((id) => {
      const job = itemsRef.current.find((i) => i.image.id === id)?.job;
      return !job || !ACTIVE.includes(job.status);
    });
    if (!targets.length) return;
    try {
      const res = await api.createJobs(targets, payload);
      res.jobs.forEach(setJob);
      res.errors.forEach((e) => {
        const name = itemsRef.current.find((i) => i.image.id === e.image_id)?.image.name ?? "Image";
        notify(`${name}: ${e.error.message}`);
      });
    } catch (err) {
      fail(err, "Could not start processing.");
    }
  }, [payload, setJob, notify, fail]);

  const retry = useCallback(async (jobId: string, device?: "auto" | "cpu") => {
    try {
      setJob(await api.retryJob(jobId, device));
    } catch (err) {
      fail(err, "Retry failed.");
    }
  }, [setJob, fail]);

  const cancel = useCallback(async (jobId: string) => {
    try {
      await api.cancelJob(jobId);
    } catch (err) {
      fail(err, "Cancel failed.");
    }
  }, [fail]);

  const activeKey = items.filter((i) => i.job && ACTIVE.includes(i.job.status)).map((i) => i.job!.id).join(",");
  useEffect(() => {
    if (!activeKey) return;
    let stopped = false;
    const tick = async () => {
      try {
        const res = await api.getJobs(activeKey.split(","));
        if (!stopped) res.jobs.forEach(setJob);
      } catch {
        /* backend status banner covers connectivity problems */
      }
    };
    const timer = setInterval(() => void tick(), 700);
    void tick();
    return () => { stopped = true; clearInterval(timer); };
  }, [activeKey, setJob]);

  // --- live output plan (resolution preview + size estimate) -------------------
  const payloadKey = JSON.stringify(payload);
  useEffect(() => {
    if (!selectedId || needsAuth) { setPlan(null); setPlanError(null); return; }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const next = await api.getPlan(selectedId, JSON.parse(payloadKey), format, quality, controller.signal);
        setPlan(next);
        setPlanError(null);
      } catch (err) {
        if (controller.signal.aborted) return;
        if (err instanceof api.ApiError && err.code === "auth_required") setNeedsAuth(true);
        setPlan(null);
        setPlanError(err instanceof api.ApiError ? err : null);
      }
    }, 180);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [selectedId, payloadKey, format, quality, system?.models, needsAuth]);

  // --- downloads -------------------------------------------------------------------
  const completed = useMemo(() => items.filter((i) => i.job?.status === "completed"), [items]);

  const downloadOne = useCallback(async (item: QueueItem) => {
    if (!item.job || downloadProgress !== null) return;
    try {
      await api.downloadResult(item.job.id, format, quality, item.image.name, onProgress);
    } catch (err) {
      fail(err, "Download failed.");
    } finally {
      setDownloadProgress(null);
    }
  }, [format, quality, fail, onProgress, downloadProgress]);

  const downloadAll = useCallback(async () => {
    if (downloadProgress !== null) return;
    try {
      await api.downloadZip(completed.map((i) => i.job!.id), format, quality, onProgress);
    } catch (err) {
      fail(err, "Download failed.");
    } finally {
      setDownloadProgress(null);
    }
  }, [completed, format, quality, fail, onProgress, downloadProgress]);

  return {
    connection, connect, needsAuth, setNeedsAuth, needsLink, ready,
    system, offline, items, selected, selectedId, setSelectedId, settings, shown, update,
    applyPreset, resetAdjustments, lockAspect, setLockAspect, dimAnchor, setDimAnchor,
    format, setFormat, quality, setQuality, downloadProgress, plan, planError, uploading, notices, dismissNotice,
    addFiles, removeItem, clearAll, enhance, retry, cancel, completed, downloadOne, downloadAll,
  };
}

export type Enhancer = ReturnType<typeof useEnhancer>;
