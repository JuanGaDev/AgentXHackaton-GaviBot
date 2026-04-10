import { Component } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatToolbarModule,
    MatButtonModule,
    MatIconModule,
  ],
  template: `
    <mat-toolbar class="app-toolbar">
      <div class="toolbar-content">
        <div class="brand">
          <div class="brand-icon">
            <mat-icon>bolt</mat-icon>
          </div>
          <div class="brand-text">
            <span class="brand-name">GaviBot</span>
            <span class="brand-subtitle">SRE Incident Intelligence</span>
          </div>
        </div>
        <nav class="nav-links">
          <a mat-button routerLink="/dashboard" routerLinkActive="nav-active" class="nav-btn">
            <mat-icon>dashboard</mat-icon>
            Dashboard
          </a>
          <a mat-button routerLink="/report" class="report-btn">
            <mat-icon>add_circle_outline</mat-icon>
            Report Incident
          </a>
        </nav>
      </div>
    </mat-toolbar>
    <main>
      <router-outlet />
    </main>
  `,
  styles: [`
    .app-toolbar {
      position: sticky;
      top: 0;
      z-index: 100;
      height: 58px;
      padding: 0 24px;
      background: #0e1520 !important;
      border-bottom: 1px solid #1e2d44 !important;
      box-shadow: 0 4px 24px rgba(0,0,0,0.5) !important;
    }
    .toolbar-content {
      display: flex;
      align-items: center;
      justify-content: space-between;
      width: 100%;
      max-width: 1200px;
      margin: 0 auto;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-icon {
      width: 34px;
      height: 34px;
      border-radius: 8px;
      background: linear-gradient(135deg, #7c6af7, #5b21b6);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 0 16px rgba(124, 106, 247, 0.5);
      mat-icon {
        font-size: 20px;
        height: 20px;
        width: 20px;
        color: white !important;
      }
    }
    .brand-text {
      display: flex;
      flex-direction: column;
      gap: 1px;
    }
    .brand-name {
      font-size: 17px;
      font-weight: 700;
      color: #e2e8f0;
      letter-spacing: -0.3px;
      line-height: 1;
    }
    .brand-subtitle {
      font-size: 10px;
      color: #5a6a82;
      font-weight: 500;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }
    .nav-links {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .nav-btn {
      color: #94a3b8 !important;
      font-size: 13px;
      font-weight: 500;
      border-radius: 8px !important;
      display: flex;
      align-items: center;
      gap: 6px;
      mat-icon { font-size: 16px; height: 16px; width: 16px; }
      &:hover { color: #e2e8f0 !important; background: rgba(255,255,255,0.05) !important; }
    }
    .nav-active {
      color: #e2e8f0 !important;
      background: rgba(124,106,247,0.15) !important;
    }
    .report-btn {
      background: linear-gradient(135deg, #7c6af7, #5b21b6) !important;
      color: white !important;
      font-size: 13px;
      font-weight: 600;
      border-radius: 8px !important;
      padding: 0 16px !important;
      height: 36px !important;
      display: flex;
      align-items: center;
      gap: 6px;
      box-shadow: 0 0 16px rgba(124,106,247,0.35);
      mat-icon { font-size: 16px; height: 16px; width: 16px; color: white !important; }
      &:hover { box-shadow: 0 0 24px rgba(124,106,247,0.55) !important; }
    }
    main {
      min-height: calc(100vh - 58px);
      background: #080c14;
    }
  `],
})
export class AppComponent {}
