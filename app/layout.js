import './globals.css';

export const metadata = {
  title: 'BTC Quant AI — Predictive Dashboard',
  description: 'Real Bitcoin data, price-agnostic features, RandomForest next-day signal & rolling accuracy.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 antialiased">{children}</body>
    </html>
  );
}
