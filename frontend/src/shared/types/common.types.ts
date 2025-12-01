// 通用型別定義

export type ToastType = 'success' | 'error' | 'info' | 'warning';

export interface ToastMessage {
  message: string;
  type: ToastType;
}

export interface FileWithPreview extends File {
  preview?: string;
}
