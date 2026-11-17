import path from "node:path";
import { fileURLToPath } from "node:url";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Pin the workspace root to this folder (a package-lock.json in the user folder confused Next.js).
  outputFileTracingRoot: path.dirname(fileURLToPath(import.meta.url)),
  // ESLint is not part of this project; type checking still runs during `next build`.
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
