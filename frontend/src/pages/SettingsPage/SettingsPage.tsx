// SettingsPage - 設定頁面

import { SettingsForm } from './SettingsForm';

export function SettingsPage() {
  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-2">設定</h1>
        <p className="text-base-content opacity-60">
          配置 API Key 和翻譯選項
        </p>
      </div>

      <SettingsForm />

      <div className="alert alert-info">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          className="stroke-current shrink-0 w-6 h-6"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          ></path>
        </svg>
        <div>
          <h3 className="font-bold">如何取得 Gemini API Key？</h3>
          <div className="text-sm">
            前往{' '}
            <a
              href="https://makersuite.google.com/app/apikey"
              target="_blank"
              rel="noopener noreferrer"
              className="link link-primary"
            >
              Google AI Studio
            </a>{' '}
            建立您的 API Key
          </div>
        </div>
      </div>
    </div>
  );
}
