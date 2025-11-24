/**
 * Marketplace Application Entry Point
 * 
 * Entry point for the standalone marketplace application.
 * This file is used when opening the marketplace in a new tab.
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import { Provider } from 'react-redux';
import { store } from './store';
import MarketplaceApp from './MarketplaceApp';
import './App.css';

ReactDOM.createRoot(document.getElementById('marketplace-root')!).render(
  <React.StrictMode>
    <Provider store={store}>
      <MarketplaceApp />
    </Provider>
  </React.StrictMode>
);


