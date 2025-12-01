// Settings 型別定義

export interface Settings {
  apiKey: string;
  nameMapping: Record<string, string>;
  globalPrompt: string;
}

export interface SettingsFormData {
  apiKey: string;
  globalPrompt?: string;
}
