/**
 * 應用程式配置
 * 集中管理 providers 和設定
 */
import { ApplicationConfig, importProvidersFrom } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { LucideAngularModule, Languages, Settings, Upload, Image as ImageIcon, X, Save } from 'lucide-angular';

import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(routes),
    provideHttpClient(),
    importProvidersFrom(LucideAngularModule.pick({ Languages, Settings, Upload, Image: ImageIcon, X, Save }))
  ],
};
