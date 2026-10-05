import path from 'node:path';
import { defineConfig } from '@playwright/test';

const frontendRoot = __dirname;
const projectRoot = path.resolve(__dirname, '..');

export default defineConfig({
  testDir: './live-e2e',
  fullyParallel: false,
  workers: 1,
  reporter: 'line',
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: 'python -m uvicorn api:app --host 127.0.0.1 --port 8000',
      cwd: projectRoot,
      url: 'http://127.0.0.1:8000/api/live',
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        REDIS_HOST: '127.0.0.1',
        REDIS_PORT: '1',
        NEO4J_PASSWORD: '',
        OLLAMA_URL: 'http://127.0.0.1:1',
        FEEDBACK_DB_PATH: 'data/local/feedback-live-smoke.sqlite3',
      },
    },
    {
      command: 'npm run dev:e2e',
      cwd: frontendRoot,
      url: 'http://127.0.0.1:4173',
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
