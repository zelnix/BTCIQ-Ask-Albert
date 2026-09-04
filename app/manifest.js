export default function manifest() {
  return {
    name: 'Ask Albert — Hucentai Crypto IQ',
    short_name: 'Ask Albert',
    description:
      'Real-time crypto market intelligence — a unified decision engine, probability forecasts, news-linked odds and an AI analyst you can ask anything. Hucentai Crypto IQ.',
    start_url: '/',
    display: 'standalone',
    background_color: '#0b1220',
    theme_color: '#0b1220',
    orientation: 'portrait-primary',
    categories: ['finance', 'productivity', 'news'],
    icons: [
      { src: '/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
      { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
      { src: '/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
    ],
  };
}
