import { Component, importProvidersFrom } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { LucideAngularModule, Languages, Settings } from 'lucide-angular';

@Component({
  selector: 'app-main-layout',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, LucideAngularModule],
  templateUrl: './main-layout.html',
  styles: [`
    :host {
      display: block;
    }
  `]
})
export class MainLayout {
  readonly Languages = Languages;
  readonly Settings = Settings;
}
