import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dashboard calls the FastAPI backend directly at http://localhost:8000
// (CORS allows this origin). `npm run dev` opens the desk in the browser.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, open: true },
})
