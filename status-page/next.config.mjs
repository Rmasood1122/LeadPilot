// status.calendarharvest.com — a SEPARATE Vercel project (root directory
// `status-page`). Not a static export: the home page and /api/status are
// rendered on the server and revalidated every 60 s so the UptimeRobot key
// stays server-side. See docs/program/STATUS_PAGE.md.

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Incident files are read with fs at render time (lib/incidents.ts). The
  // file tracer cannot see a path built from process.cwd(), so ship them
  // into every server function explicitly.
  outputFileTracingIncludes: {
    "/**": ["./incidents/**/*.md"],
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};

export default nextConfig;
