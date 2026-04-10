import { Injectable } from '@angular/core';
import { Observable, Subject, timer } from 'rxjs';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';

@Injectable({ providedIn: 'root' })
export class WebSocketService {
  private sockets: Map<string, WebSocketSubject<unknown>> = new Map();

  connect(incidentId: string): Observable<unknown> {
    const wsUrl = `ws://${window.location.host}/ws/incidents/${incidentId}`;
    
    if (!this.sockets.has(incidentId)) {
      const socket = webSocket(wsUrl);
      this.sockets.set(incidentId, socket);
    }
    return this.sockets.get(incidentId)!.asObservable();
  }

  disconnect(incidentId: string): void {
    const socket = this.sockets.get(incidentId);
    if (socket) {
      socket.complete();
      this.sockets.delete(incidentId);
    }
  }
}
