import React from 'react';

// The currently-selected coin flows through this context so deep components
// (Albert insights, Ask Albert chat, section views) fetch data for the right asset.
export const SymbolContext = React.createContext('BTC');
