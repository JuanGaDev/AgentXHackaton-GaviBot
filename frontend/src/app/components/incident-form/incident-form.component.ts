import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatChipsModule } from '@angular/material/chips';
import { MatSnackBarModule, MatSnackBar } from '@angular/material/snack-bar';
import { MatDividerModule } from '@angular/material/divider';
import { IncidentService } from '../../services/incident.service';
import { Severity } from '../../models/incident.model';

@Component({
  selector: 'app-incident-form',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatIconModule,
    MatProgressBarModule,
    MatChipsModule,
    MatSnackBarModule,
    MatDividerModule,
  ],
  templateUrl: './incident-form.component.html',
  styleUrls: ['./incident-form.component.scss'],
})
export class IncidentFormComponent implements OnInit {
  form!: FormGroup;
  submitting = false;
  uploadedFiles: File[] = [];
  dragOver = false;

  severityOptions: { value: Severity; label: string; description: string; color: string }[] = [
    { value: 'P0', label: 'P0 - Critical', description: 'Complete outage, data loss, payments down', color: '#ff1744' },
    { value: 'P1', label: 'P1 - High', description: 'Major feature broken, significant revenue impact', color: '#ff6d00' },
    { value: 'P2', label: 'P2 - Medium', description: 'Important feature degraded, workaround available', color: '#ffa000' },
    { value: 'P3', label: 'P3 - Low', description: 'Minor issue, cosmetic, low user impact', color: '#ffd600' },
    { value: 'P4', label: 'P4 - Info', description: 'Enhancement, question, no impact', color: '#00c853' },
  ];

  constructor(
    private fb: FormBuilder,
    private incidentService: IncidentService,
    private router: Router,
    private snackBar: MatSnackBar
  ) {}

  ngOnInit(): void {
    this.form = this.fb.group({
      title: ['', [Validators.required, Validators.minLength(5), Validators.maxLength(500)]],
      description: ['', [Validators.required, Validators.minLength(20), Validators.maxLength(10000)]],
      reporter_name: ['', [Validators.required, Validators.minLength(2)]],
      reporter_email: ['', [Validators.required, Validators.email]],
      severity_hint: [null],
    });
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files) {
      this.addFiles(Array.from(input.files));
    }
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.dragOver = true;
  }

  onDragLeave(event: DragEvent): void {
    this.dragOver = false;
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.dragOver = false;
    const files = event.dataTransfer?.files;
    if (files) {
      this.addFiles(Array.from(files));
    }
  }

  addFiles(files: File[]): void {
    const allowed = ['image/png', 'image/jpeg', 'image/gif', 'image/webp', 'text/plain', 'application/json', 'text/csv'];
    for (const file of files) {
      if (allowed.includes(file.type) || file.name.endsWith('.log')) {
        if (this.uploadedFiles.length < 5) {
          this.uploadedFiles.push(file);
        }
      } else {
        this.snackBar.open(`File type not supported: ${file.name}`, 'Dismiss', { duration: 3000 });
      }
    }
  }

  removeFile(index: number): void {
    this.uploadedFiles.splice(index, 1);
  }

  getFileIcon(file: File): string {
    if (file.type.startsWith('image/')) return 'image';
    if (file.name.endsWith('.log') || file.name.endsWith('.txt')) return 'description';
    if (file.name.endsWith('.json')) return 'data_object';
    return 'attach_file';
  }

  formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.submitting = true;

    this.incidentService
      .createIncident({
        ...this.form.value,
        attachments: this.uploadedFiles,
      })
      .subscribe({
        next: (incident) => {
          this.snackBar.open('Incident submitted! Triage in progress...', 'View', {
            duration: 5000,
          }).onAction().subscribe(() => {
            this.router.navigate(['/incidents', incident.id]);
          });
          this.router.navigate(['/incidents', incident.id]);
        },
        error: (err) => {
          this.submitting = false;
          const message = err.error?.detail || 'Failed to submit incident. Please try again.';
          this.snackBar.open(message, 'Dismiss', { duration: 5000 });
        },
      });
  }
}
