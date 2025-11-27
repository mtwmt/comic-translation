import { Component, importProvidersFrom } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LucideAngularModule, Upload, Image as ImageIcon, X } from 'lucide-angular';

@Component({
  selector: 'app-translator',
  standalone: true,
  imports: [CommonModule, LucideAngularModule],
  templateUrl: './translator.html'
})
export class Translator {
  readonly Upload = Upload;
  readonly Image = ImageIcon;
  readonly X = X;
}
