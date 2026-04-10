import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule, TitleCasePipe, DatePipe, SlicePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatBadgeModule } from '@angular/material/badge';
import { Subscription, interval } from 'rxjs';
import { switchMap, startWith } from 'rxjs/operators';
import { IncidentService } from '../../services/incident.service';
import { Incident, Stats } from '../../models/incident.model';

@Component({
  selector: 'app-incident-list',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    FormsModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatTableModule,
    MatChipsModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatFormFieldModule,
    MatTooltipModule,
    MatBadgeModule,
    TitleCasePipe,
    DatePipe,
    SlicePipe,
  ],
  templateUrl: './incident-list.component.html',
  styleUrls: ['./incident-list.component.scss'],
})
export class IncidentListComponent implements OnInit, OnDestroy {
  incidents: Incident[] = [];
  stats: Stats | null = null;
  loading = true;
  statusFilter = '';
  displayedColumns = ['status', 'severity', 'title', 'team', 'reporter', 'ticket', 'created', 'actions'];

  private sub?: Subscription;

  constructor(private incidentService: IncidentService) {}

  ngOnInit(): void {
    this.loadStats();
    this.sub = interval(5000)
      .pipe(
        startWith(0),
        switchMap(() => this.incidentService.getIncidents(this.statusFilter || undefined))
      )
      .subscribe({
        next: (data) => {
          this.incidents = data;
          this.loading = false;
        },
        error: () => {
          this.loading = false;
        },
      });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  loadStats(): void {
    this.incidentService.getStats().subscribe({
      next: (s) => (this.stats = s),
    });
  }

  applyFilter(): void {
    this.loading = true;
    this.incidentService.getIncidents(this.statusFilter || undefined).subscribe({
      next: (data) => {
        this.incidents = data;
        this.loading = false;
      },
    });
  }

  getSeverityClass(severity: string | null): string {
    return severity ? severity.toLowerCase() : 'unknown';
  }

  getStatusClass(status: string): string {
    return status.toLowerCase().replace('_', '-');
  }

  formatDate(dateStr: string): string {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return 'Just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return `${diffH}h ago`;
    return date.toLocaleDateString();
  }

  isActiveStatus(status: string): boolean {
    return ['received', 'triaging'].includes(status);
  }

  get activeCount(): number {
    return this.incidents.filter((i) => this.isActiveStatus(i.status)).length;
  }

  get criticalCount(): number {
    return this.incidents.filter((i) => i.severity_final === 'P0' || i.severity_final === 'P1').length;
  }
}
