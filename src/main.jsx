import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'


window.storage = {
  get: async (key) => {
    const value = localStorage.getItem(key);
    return value === null ? null : { value };
  },
  set: async (key, value) => {
    localStorage.setItem(key, value);
    return { value };
  },
};


createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
