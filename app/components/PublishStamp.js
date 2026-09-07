'use client';
// Live "Published {date} · {time}" stamp, shared across every page footer.
// null on first render to avoid SSR hydration mismatch; updates every 60s.
import React, { useEffect, useState } from 'react';

export default function PublishStamp({ className = '' }) {
  const [now, setNow] = useState(null);
  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 60000);
    return () => clearInterval(t);
  }, []);
  if (!now) return null;
  const date = now.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
  const time = now.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  return (
    <p className={`text-[10px] leading-tight text-slate-500 ${className}`} suppressHydrationWarning>
      <span className="text-slate-400">Published</span> {date} · {time}
    </p>
  );
}
