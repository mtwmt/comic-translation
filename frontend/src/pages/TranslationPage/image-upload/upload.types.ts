// Image Upload 型別定義

export interface UploadedImage {
  file: File;
  preview: string;
  id: string;
}

export interface UploadError {
  message: string;
  file?: string;
}
