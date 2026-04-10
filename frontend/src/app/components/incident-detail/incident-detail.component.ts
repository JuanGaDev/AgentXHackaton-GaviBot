import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule, TitleCasePipe } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Subscription } from 'rxjs';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { IncidentService } from '../../services/incident.service';
import { Incident, AuditLogEntry } from '../../models/incident.model';

@Component({
  selector: 'app-incident-detail',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatChipsModule,
    MatDividerModule,
    MatTooltipModule,
    MatSnackBarModule,
    TitleCasePipe,
  ],
  templateUrl: './incident-detail.component.html',
  styleUrls: ['./incident-detail.component.scss'],
})
export class IncidentDetailComponent implements OnInit, OnDestroy {
  incident: Incident | null = null;
  auditLogs: AuditLogEntry[] = [];
  notificationPreviews: AuditLogEntry[] = [];
  loading = true;
  resolving = false;
  private sub?: Subscription;

  pipelineSteps = [
    { label: 'Received', icon: 'inbox' },
    { label: 'Triage', icon: 'psychology' },
    { label: 'Triaged', icon: 'fact_check' },
    { label: 'Ticket', icon: 'confirmation_number' },
    { label: 'Notified', icon: 'notifications_active' },
    { label: 'Resolved', icon: 'check_circle' },
  ];

  constructor(
    private route: ActivatedRoute,
    private incidentService: IncidentService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id')!;
    this.loadAuditLog(id);

    this.sub = this.incidentService.pollIncident(id, 3000).subscribe({
      next: (data: Incident) => {
        this.incident = data;
        this.loading = false;
        // Reload audit log on status change
        if (data.status !== 'received' && data.status !== 'triaging') {
          this.loadAuditLog(id);
        }
      },
      error: () => {
        this.loading = false;
      },
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  loadAuditLog(id: string): void {
    this.incidentService.getAuditLog(id).subscribe({
      next: (logs: AuditLogEntry[]) => {
        this.notificationPreviews = logs.filter((l: AuditLogEntry) => l.stage === 'notification_preview');
        this.auditLogs = logs.filter((l: AuditLogEntry) => l.stage !== 'notification_preview');
      },
    });
  }

  getNotificationIcon(type: unknown): string {
    if (type === 'reporter_resolved') return 'mark_email_read';
    if (type === 'team_notification') return 'groups';
    return 'email';
  }

  getNotificationColor(type: unknown): string {
    if (type === 'reporter_resolved') return '#059669';
    if (type === 'team_notification') return '#2563eb';
    return '#7c3aed';
  }

  getNotificationLabel(type: unknown): string {
    if (type === 'reporter_resolved') return 'Resolution Notice';
    if (type === 'team_notification') return 'Team Alert';
    return 'Confirmation';
  }

  getSeverityClass(severity: string | null): string {
    return severity ? severity.toLowerCase() : 'unknown';
  }

  getStatusClass(status: string): string {
    return status.toLowerCase().replace('_', '-');
  }

  isInProgress(): boolean {
    return ['received', 'triaging'].includes(this.incident?.status || '');
  }

  formatDate(dateStr: string): string {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleString();
  }

  canResolve(): boolean {
    return ['ticket_created', 'notified', 'triaged'].includes(this.incident?.status || '');
  }

  resolveIncident(): void {
    if (!this.incident) return;
    this.resolving = true;
    this.incidentService.resolveIncident(this.incident.id).subscribe({
      next: (updated: Incident) => {
        this.incident = updated;
        this.resolving = false;
        this.loadAuditLog(updated.id);
        this.snackBar.open('Incident resolved! Reporter notification sent.', 'OK', { duration: 4000 });
      },
      error: (err: { error?: { detail?: string } }) => {
        this.resolving = false;
        this.snackBar.open(err.error?.detail || 'Failed to resolve incident.', 'Dismiss', { duration: 4000 });
      },
    });
  }

  getPipelineStep(): number {
    const statusSteps: Record<string, number> = {
      received: 1,
      triaging: 2,
      triaged: 3,
      ticket_created: 4,
      notified: 5,
      resolved: 6,
      failed: 0,
    };
    return statusSteps[this.incident?.status || ''] ?? 0;
  }
}
