// 應用配置常量

export const APP_CONFIG = {
  name: import.meta.env.VITE_APP_NAME || '漫畫翻譯器',
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  isDev: import.meta.env.DEV,
} as const;

export const ROUTES = {
  HOME: '/',
  SETTINGS: '/settings',
} as const;

export const STORAGE_KEYS = {
  API_KEY: 'gemini_api_key',
  SETTINGS: 'app_settings',
  NAME_MAPPING: 'name_mapping',
} as const;

export const FILE_CONSTRAINTS = {
  MAX_SIZE: 10 * 1024 * 1024, // 10MB
  ACCEPTED_TYPES: ['image/png', 'image/jpeg', 'image/jpg', 'image/webp'],
  ACCEPTED_EXTENSIONS: ['.png', '.jpg', '.jpeg', '.webp'],
} as const;
