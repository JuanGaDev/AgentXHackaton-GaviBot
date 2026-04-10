import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    redirectTo: '/dashboard',
    pathMatch: 'full',
  },
  {
    path: 'dashboard',
    loadComponent: () =>
      import('./components/incident-list/incident-list.component').then(
        (m) => m.IncidentListComponent
      ),
  },
  {
    path: 'report',
    loadComponent: () =>
      import('./components/incident-form/incident-form.component').then(
        (m) => m.IncidentFormComponent
      ),
  },
  {
    path: 'incidents/:id',
    loadComponent: () =>
      import('./components/incident-detail/incident-detail.component').then(
        (m) => m.IncidentDetailComponent
      ),
  },
  {
    path: '**',
    redirectTo: '/dashboard',
  },
];
