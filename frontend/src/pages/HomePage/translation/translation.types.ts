// Translation 型別定義

export interface TranslationRequest {
  image: File;
  nameMapping?: Record<string, string>;
  extraPrompt?: string;
}

export interface TranslationResponse {
  success: boolean;
  outputPath?: string;
  filename?: string;
  error?: string;
}

export interface TranslationResult {
  imageUrl: string;
  filename: string;
  timestamp: Date;
}
