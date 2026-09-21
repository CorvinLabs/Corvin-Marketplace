/**
 * Workflows API Client — Extracted from console
 *
 * Makes HTTP calls to plugin routes instead of console.
 * Assumes CSRF token available via auth context.
 */

import { getCsrfToken } from '@/hooks/useAuth';

const BASE_URL = '/v1/console/workflows';

export interface Workflow {
  wid: string;
  title: string;
  description: string;
  status: 'DRAFT' | 'ACTIVE' | 'PAUSED';
  created_at: string;
  updated_at: string;
  node_count: number;
  phase: string;
}

export interface WorkflowRun {
  rid: string;
  wid: string;
  status: 'RUNNING' | 'COMPLETED' | 'FAILED' | 'PAUSED';
  started_at: string;
  completed_at?: string;
  node_results: Record<string, any>;
}

// ────────────────────────────────────────────────────────────────────────────
// CRUD Operations
// ────────────────────────────────────────────────────────────────────────────

export async function listWorkflows(): Promise<Workflow[]> {
  const res = await fetch(`${BASE_URL}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  });
  if (!res.ok) throw new Error(`List workflows failed: ${res.statusText}`);
  const data = await res.json();
  return data.workflows || [];
}

export async function getWorkflow(wid: string): Promise<Workflow> {
  const res = await fetch(`${BASE_URL}/${wid}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  });
  if (!res.ok) throw new Error(`Get workflow failed: ${res.statusText}`);
  return res.json();
}

export async function createWorkflow(title: string, description: string = ''): Promise<{ wid: string }> {
  const csrf = getCsrfToken();
  const res = await fetch(`${BASE_URL}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrf,
    },
    credentials: 'include',
    body: JSON.stringify({ title, description }),
  });
  if (!res.ok) throw new Error(`Create workflow failed: ${res.statusText}`);
  return res.json();
}

export async function updateWorkflow(
  wid: string,
  title: string,
  description: string,
): Promise<Workflow> {
  const csrf = getCsrfToken();
  const res = await fetch(`${BASE_URL}/${wid}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrf,
    },
    credentials: 'include',
    body: JSON.stringify({ title, description }),
  });
  if (!res.ok) throw new Error(`Update workflow failed: ${res.statusText}`);
  return res.json();
}

export async function deleteWorkflow(wid: string): Promise<void> {
  const csrf = getCsrfToken();
  const res = await fetch(`${BASE_URL}/${wid}`, {
    method: 'DELETE',
    headers: { 'X-CSRF-Token': csrf },
    credentials: 'include',
  });
  if (!res.ok) throw new Error(`Delete workflow failed: ${res.statusText}`);
}

// ────────────────────────────────────────────────────────────────────────────
// YAML Management
// ────────────────────────────────────────────────────────────────────────────

export async function getWorkflowYaml(wid: string): Promise<string> {
  const res = await fetch(`${BASE_URL}/${wid}/yaml`, {
    method: 'GET',
    credentials: 'include',
  });
  if (!res.ok) throw new Error(`Get YAML failed: ${res.statusText}`);
  return res.text();
}

export async function updateWorkflowYaml(wid: string, yaml: string): Promise<Workflow> {
  const csrf = getCsrfToken();
  const res = await fetch(`${BASE_URL}/${wid}/yaml`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/x-yaml',
      'X-CSRF-Token': csrf,
    },
    credentials: 'include',
    body: yaml,
  });
  if (!res.ok) throw new Error(`Update YAML failed: ${res.statusText}`);
  return res.json();
}

// ────────────────────────────────────────────────────────────────────────────
// Runs
// ────────────────────────────────────────────────────────────────────────────

export async function startRun(wid: string, options?: Record<string, any>): Promise<{ rid: string }> {
  const csrf = getCsrfToken();
  const res = await fetch(`${BASE_URL}/${wid}/runs`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrf,
    },
    credentials: 'include',
    body: JSON.stringify(options || {}),
  });
  if (!res.ok) throw new Error(`Start run failed: ${res.statusText}`);
  return res.json();
}

export async function listRuns(wid: string): Promise<WorkflowRun[]> {
  const res = await fetch(`${BASE_URL}/${wid}/runs`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  });
  if (!res.ok) throw new Error(`List runs failed: ${res.statusText}`);
  const data = await res.json();
  return data.runs || [];
}

export async function getRun(wid: string, rid: string): Promise<WorkflowRun> {
  const res = await fetch(`${BASE_URL}/${wid}/runs/${rid}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  });
  if (!res.ok) throw new Error(`Get run failed: ${res.statusText}`);
  return res.json();
}

export async function deleteRun(wid: string, rid: string): Promise<void> {
  const csrf = getCsrfToken();
  const res = await fetch(`${BASE_URL}/${wid}/runs/${rid}`, {
    method: 'DELETE',
    headers: { 'X-CSRF-Token': csrf },
    credentials: 'include',
  });
  if (!res.ok) throw new Error(`Delete run failed: ${res.statusText}`);
}

// ────────────────────────────────────────────────────────────────────────────
// Scheduling (Phase 4)
// ────────────────────────────────────────────────────────────────────────────

export async function getSchedule(wid: string): Promise<{ schedule: string | null }> {
  const res = await fetch(`${BASE_URL}/${wid}/schedule`, {
    method: 'GET',
    credentials: 'include',
  });
  if (!res.ok) return { schedule: null };
  return res.json();
}

export async function setSchedule(wid: string, cron: string): Promise<void> {
  const csrf = getCsrfToken();
  const res = await fetch(`${BASE_URL}/${wid}/schedule`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrf,
    },
    credentials: 'include',
    body: JSON.stringify({ cron }),
  });
  if (!res.ok) throw new Error(`Set schedule failed: ${res.statusText}`);
}

export async function removeSchedule(wid: string): Promise<void> {
  const csrf = getCsrfToken();
  const res = await fetch(`${BASE_URL}/${wid}/schedule`, {
    method: 'DELETE',
    headers: { 'X-CSRF-Token': csrf },
    credentials: 'include',
  });
  if (!res.ok) throw new Error(`Remove schedule failed: ${res.statusText}`);
}

// ────────────────────────────────────────────────────────────────────────────
// Export/Import (Phase 5)
// ────────────────────────────────────────────────────────────────────────────

export async function exportAwpkg(wid: string): Promise<Blob> {
  const res = await fetch(`${BASE_URL}/${wid}/export.awpkg`, {
    method: 'GET',
    credentials: 'include',
  });
  if (!res.ok) throw new Error(`Export failed: ${res.statusText}`);
  return res.blob();
}

export async function importWorkflow(file: File): Promise<{ wid: string }> {
  const csrf = getCsrfToken();
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${BASE_URL}/import`, {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrf },
    credentials: 'include',
    body: formData,
  });
  if (!res.ok) throw new Error(`Import failed: ${res.statusText}`);
  return res.json();
}
