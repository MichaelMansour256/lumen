"use client";

import { useEffect, useState } from "react";

import { fetchImageUrl } from "@/lib/api";

/** Loads an API image with the access key and exposes it as an object URL. */
export function useAuthedImage(path: string | null) {
  const [state, setState] = useState<{ url: string | null; error: string | null }>({ url: null, error: null });
  useEffect(() => {
    setState({ url: null, error: null });
    if (!path) return;
    const controller = new AbortController();
    let objectUrl: string | null = null;
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, 120_000);
    fetchImageUrl(path, controller.signal)
      .then((url) => {
        if (controller.signal.aborted) URL.revokeObjectURL(url);
        else { objectUrl = url; setState({ url, error: null }); }
      })
      .catch((err: Error) => {
        if (timedOut) setState({ url: null, error: "the connection is too slow (no data for 2 minutes)." });
        else if (!controller.signal.aborted) setState({ url: null, error: err.message || "Could not load the image." });
      })
      .finally(() => clearTimeout(timer));
    return () => {
      clearTimeout(timer);
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);
  return state;
}
