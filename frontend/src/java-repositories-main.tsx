/**
 * Main entry point for Java Repositories page
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import { Provider } from 'react-redux';
import { store } from './store';
import JavaRepositoriesPage from './pages/JavaRepositoriesPage';
import './App.css';

ReactDOM.createRoot(document.getElementById('java-repositories-root')!).render(
  <React.StrictMode>
    <Provider store={store}>
      <JavaRepositoriesPage />
    </Provider>
  </React.StrictMode>
);

