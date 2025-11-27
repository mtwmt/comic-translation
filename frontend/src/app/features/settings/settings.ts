import { Component, importProvidersFrom } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { LucideAngularModule, Save } from 'lucide-angular';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, LucideAngularModule],
  templateUrl: './settings.html'
})
export class Settings {
  settingsForm: FormGroup;
  isSaving = false;
  readonly Save = Save;

  constructor(private fb: FormBuilder) {
    this.settingsForm = this.fb.group({
      apiKey: ['', [Validators.required, Validators.minLength(10)]]
    });
  }

  isFieldInvalid(fieldName: string): boolean {
    const field = this.settingsForm.get(fieldName);
    return !!(field && field.invalid && (field.dirty || field.touched));
  }

  saveSettings() {
    if (this.settingsForm.valid) {
      this.isSaving = true;
      setTimeout(() => {
        this.isSaving = false;
      }, 1000);
    }
  }
}
