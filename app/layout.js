import './globals.css';

export const metadata = {
  title: 'BTCIQ — Bitcoin Intelligence, powered by BitCentAI',
  description: 'BTCIQ: real Bitcoin data, a unified decision engine, probability forecasts, news-linked odds and an AI analyst — powered by BitCentAI, our Bitcoin-Centred Intelligence Engine.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 antialiased">{children}</body>
    </html>
  );
}
