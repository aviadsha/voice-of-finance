import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Produces a self-contained server in .next/standalone for the Docker image.
  output: "standalone",
  poweredByHeader: false,
};

export default nextConfig;
