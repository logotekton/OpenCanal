import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@opencanal/db", "@opencanal/shared"],
  output: "standalone",
};

export default nextConfig;
