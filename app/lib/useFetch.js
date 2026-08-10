'use client';

import React from 'react';

// Small fetch-on-mount hook used across the dashboard. Returns [data, loading].
// Re-runs when any value in `deps` changes; safely ignores results after unmount.
export function useFetch(url, deps = []) {
  const [d, setD] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    let alive = true; setLoading(true);
    fetch(url, { cache: 'no-store' }).then((r) => r.json())
      .then((j) => { if (alive) { setD(j); setLoading(false); } })
      .catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, deps); // eslint-disable-line
  return [d, loading];
}
