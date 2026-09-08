'use client';
// Small reusable error boundary so ONE misbehaving sub-panel (e.g. a strategy or
// basket with unexpected data) degrades gracefully instead of taking down the
// entire section. The `label` is logged + shown so we can see exactly which
// sub-panel failed.
import React from 'react';

export default class PanelBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('PanelBoundary caught:', this.props.label || '', error, info);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.silent) return null;
      return (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/[0.06] p-4 text-sm">
          <p className="font-semibold text-amber-300">
            This part hit a snag{this.props.label ? ` (${this.props.label})` : ''}.
          </p>
          <p className="mt-1 text-slate-400">The rest of the page is still live.</p>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="mt-3 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800"
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
