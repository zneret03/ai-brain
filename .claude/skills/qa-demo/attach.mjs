#!/usr/bin/env node
// Uploads a QA demo's media to one Jira ticket and prints, per file, the attachment id and the Media
// Services id an ADF media node needs. Refuses a ticket outside the QA gate the environment sets.
// Usage: node attach.mjs <KEY> <file>...   Needs JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN and QA_GATE_STATUS;
// QA_GATE_FIELD with QA_GATE_VALUE adds a field to the gate (ai-brain/profile/TRACKER.md). Reuses same-named files.

import fs from 'node:fs';
import path from 'node:path';

const MIME = { '.mp4': 'video/mp4', '.webm': 'video/webm', '.gif': 'image/gif', '.png': 'image/png' };

const [key, ...files] = process.argv.slice(2);
if (!/^[A-Z][A-Z0-9]+-\d+$/.test(key ?? '') || files.length === 0) {
  console.error('usage: node attach.mjs <KEY> <file>...');
  process.exit(2);
}
const { JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, QA_GATE_STATUS, QA_GATE_FIELD, QA_GATE_VALUE } = process.env;
if (!JIRA_BASE_URL || !QA_GATE_STATUS || (QA_GATE_FIELD && !QA_GATE_VALUE)) {
  console.error('set JIRA_BASE_URL and QA_GATE_STATUS, and QA_GATE_VALUE with QA_GATE_FIELD: ai-brain/profile/TRACKER.md, QA gates.');
  process.exit(2);
}
const JIRA_BASE = JIRA_BASE_URL.replace(/\/+$/, '');
if (!JIRA_EMAIL || !JIRA_API_TOKEN) {
  console.error('JIRA_EMAIL and JIRA_API_TOKEN are not set: post the comment without attachments and attach the files by hand.');
  process.exit(2);
}
const missing = files.filter((file) => !fs.existsSync(file));
if (missing.length) {
  console.error(`no such file: ${missing.join(', ')}`);
  process.exit(2);
}

const AUTH = `Basic ${Buffer.from(`${JIRA_EMAIL}:${JIRA_API_TOKEN}`).toString('base64')}`;

async function api(pathname, init = {}) {
  const res = await fetch(`${JIRA_BASE}${pathname}`, {
    ...init,
    headers: { Authorization: AUTH, Accept: 'application/json', ...(init.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${init.method ?? 'GET'} ${pathname} -> HTTP ${res.status}: ${(await res.text()).slice(0, 300)}`);
  return res;
}

// The id lives only in the content URL's redirect; null makes the comment link the file instead.
async function mediaUuid(contentUrl) {
  const res = await fetch(contentUrl, { redirect: 'manual', headers: { Authorization: AUTH } }).catch(() => null);
  const match = (res?.headers.get('location') ?? '').match(/\/file\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\//i);
  return match ? match[1] : null;
}

try {
  const fields = ['status', 'attachment', ...(QA_GATE_FIELD ? [QA_GATE_FIELD] : [])].join(',');
  const issue = await (await api(`/rest/api/3/issue/${key}?fields=${fields}`)).json();
  const status = issue.fields?.status?.name;
  const qaStatus = QA_GATE_FIELD ? issue.fields?.[QA_GATE_FIELD]?.value : undefined;
  if (status !== QA_GATE_STATUS || (QA_GATE_FIELD && qaStatus !== QA_GATE_VALUE)) {
    const need = QA_GATE_FIELD ? `"${QA_GATE_STATUS}" and "${QA_GATE_VALUE}"` : `"${QA_GATE_STATUS}"`;
    console.error(`${key} is "${status}"${QA_GATE_FIELD ? ` with QA Status "${qaStatus ?? 'empty'}"` : ''}; uploads need ${need}.`);
    process.exit(2);
  }

  const existing = new Map((issue.fields?.attachment ?? []).map((attachment) => [attachment.filename, attachment]));
  const uploaded = [];
  for (const file of files) {
    const name = path.basename(file);
    let attachment = existing.get(name);
    if (!attachment) {
      const form = new FormData();
      form.append('file', new Blob([fs.readFileSync(file)], { type: MIME[path.extname(name)] ?? 'application/octet-stream' }), name);
      const res = await api(`/rest/api/3/issue/${key}/attachments`, {
        method: 'POST',
        headers: { 'X-Atlassian-Token': 'no-check' },
        body: form,
      });
      [attachment] = await res.json();
    }
    uploaded.push({
      file: name,
      attachmentId: attachment.id,
      size: attachment.size,
      reused: existing.has(name),
      mediaUuid: attachment.content ? await mediaUuid(attachment.content) : null,
    });
  }
  console.log(JSON.stringify(uploaded, null, 2));
} catch (err) {
  console.error(String(err?.message ?? err));
  process.exit(1);
}
