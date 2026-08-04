const nextConfig = {
  output: 'standalone',
  // Allow the cross-origin preview hosts to reach the dev server (/_next/* HMR etc.)
  // Without this, Next.js 15 blocks cross-origin dev asset requests, which breaks
  // Fast Refresh and causes the preview to reload/reset repeatedly.
  allowedDevOrigins: [
    '*.preview.emergentagent.com',
    '*.preview.emergentcf.cloud',
    '*.emergentagent.com',
    '*.emergentcf.cloud',
  ],
  images: {
    unoptimized: true,
    remotePatterns: [
      { protocol: 'https', hostname: 'avatars.githubusercontent.com', pathname: '/**' },
    ],
  },
  // Renamed from experimental.serverComponentsExternalPackages in Next 15
  serverExternalPackages: ['mongodb'],
  webpack(config, { dev }) {
    if (dev) {
      // Use native file watching (avoid polling, which can trigger phantom rebuilds).
      config.watchOptions = {
        aggregateTimeout: 300,
        ignored: ['**/node_modules', '**/.git', '**/.next'],
      };
    }
    return config;
  },
  onDemandEntries: {
    // Keep compiled pages warm for an hour so the dev preview does not keep
    // disposing + recompiling the page (which forces periodic HMR reloads).
    maxInactiveAge: 60 * 60 * 1000,
    pagesBufferLength: 5,
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "ALLOWALL" },
          { key: "Content-Security-Policy", value: "frame-ancestors *;" },
          { key: "Access-Control-Allow-Origin", value: process.env.CORS_ORIGINS || "*" },
          { key: "Access-Control-Allow-Methods", value: "GET, POST, PUT, DELETE, OPTIONS" },
          { key: "Access-Control-Allow-Headers", value: "*" },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
