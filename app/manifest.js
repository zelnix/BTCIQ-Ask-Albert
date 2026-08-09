export default function manifest() {
  return {
    name: 'BTCIQ — Bitcoin Intelligence',
    short_name: 'BTCIQ',
    description:
      'Real Bitcoin data, a unified decision engine, probability forecasts, news-linked odds and an AI analyst — powered by BitCentAI.',
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
