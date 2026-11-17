import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  // a small self-contained server for the Docker image (Vercel builds its own way)
  output: process.env.VERCEL ? undefined : "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
