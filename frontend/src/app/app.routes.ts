import { Routes } from '@angular/router';
import { MainLayout } from './layout/main-layout/main-layout';

export const routes: Routes = [
  {
    path: '',
    component: MainLayout,
    children: [
      { path: '', redirectTo: 'translator', pathMatch: 'full' },
      {
        path: 'translator',
        loadComponent: () => import('./features/translator/translator').then(m => m.Translator)
      },
      {
        path: 'settings',
        loadComponent: () => import('./features/settings/settings').then(m => m.Settings)
      }
    ]
  },
  {
    path: '**',
    redirectTo: 'translator'
  }
];
