import React from 'react';
import ReactDOM from 'react-dom/client';
import { Provider } from 'react-redux';
import { store } from './store';
import DeveloperTools from './components/DeveloperTools';
import './components/DeveloperTools.css';
import './App.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Provider store={store}>
      <DeveloperTools />
    </Provider>
  </React.StrictMode>
);

