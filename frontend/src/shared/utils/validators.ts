// 驗證工具函數

import { FILE_CONSTRAINTS } from '../constants/config';

export function isValidImageFile(file: File): boolean {
  return FILE_CONSTRAINTS.ACCEPTED_TYPES.includes(file.type);
}

export function isValidFileSize(file: File): boolean {
  return file.size <= FILE_CONSTRAINTS.MAX_SIZE;
}

export function validateImageFile(file: File): {
  valid: boolean;
  error?: string;
} {
  if (!isValidImageFile(file)) {
    return {
      valid: false,
      error: `不支援的檔案格式。請使用 ${FILE_CONSTRAINTS.ACCEPTED_EXTENSIONS.join(', ')}`,
    };
  }

  if (!isValidFileSize(file)) {
    return {
      valid: false,
      error: `檔案太大。最大支援 ${FILE_CONSTRAINTS.MAX_SIZE / 1024 / 1024}MB`,
    };
  }

  return { valid: true };
}
