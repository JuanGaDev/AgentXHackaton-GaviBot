import { Injectable } from '@angular/core';
import { HttpClient, HttpEventType } from '@angular/common/http';
import { Observable, interval, switchMap, startWith } from 'rxjs';
import { Incident, AuditLogEntry, CreateIncidentForm, Stats } from '../models/incident.model';

@Injectable({ providedIn: 'root' })
export class IncidentService {
  private readonly apiBase = '/api/v1';

  constructor(private http: HttpClient) {}

  createIncident(form: CreateIncidentForm): Observable<Incident> {
    const formData = new FormData();
    formData.append('title', form.title);
    formData.append('description', form.description);
    formData.append('reporter_name', form.reporter_name);
    formData.append('reporter_email', form.reporter_email);
    if (form.severity_hint) {
      formData.append('severity_hint', form.severity_hint);
    }
    if (form.attachments) {
      for (const file of form.attachments) {
        formData.append('attachments', file, file.name);
      }
    }
    return this.http.post<Incident>(`${this.apiBase}/incidents/`, formData);
  }

  getIncidents(status?: string): Observable<Incident[]> {
    if (status) {
      return this.http.get<Incident[]>(`${this.apiBase}/incidents/`, {
        params: { status },
      });
    }
    return this.http.get<Incident[]>(`${this.apiBase}/incidents/`);
  }

  getIncident(id: string): Observable<Incident> {
    return this.http.get<Incident>(`${this.apiBase}/incidents/${id}`);
  }

  getAuditLog(id: string): Observable<AuditLogEntry[]> {
    return this.http.get<AuditLogEntry[]>(`${this.apiBase}/incidents/${id}/audit`);
  }

  getStats(): Observable<Stats> {
    return this.http.get<Stats>(`${this.apiBase}/stats`);
  }

  resolveIncident(id: string): Observable<Incident> {
    return this.http.post<Incident>(`${this.apiBase}/incidents/${id}/resolve`, {});
  }

  pollIncident(id: string, intervalMs = 3000): Observable<Incident> {
    return interval(intervalMs).pipe(
      startWith(0),
      switchMap(() => this.getIncident(id))
    );
  }
}
