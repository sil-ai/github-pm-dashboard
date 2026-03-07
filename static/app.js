const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);
const content = $('#content');
const loading = $('#loading');

// State
let activeRepos = [];
let orgMembers = [];

// Utils
function daysAgo(dateStr) {
  if (!dateStr) return 0;
  return Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000);
}

function timeAgo(dateStr) {
  if (!dateStr) return '';
  const ms = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function fmtDate(dateStr) {
  if (!dateStr) return 'N/A';
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function repoName(r) {
  if (typeof r === 'string') return r;
  return r?.name || r?.fullName?.split('/')[1] || 'unknown';
}

function assigneeStr(assignees) {
  if (!assignees || !assignees.length) return '<span class="text-gray-500">unassigned</span>';
  return assignees.map(a => `@${a.login || a}`).join(', ');
}

function priorityClass(labels) {
  if (!labels) return '';
  for (const l of labels) {
    const n = l.name || l;
    if (n.startsWith('P0')) return 'priority-p0';
    if (n.startsWith('P1')) return 'priority-p1';
    if (n.startsWith('P2')) return 'priority-p2';
    if (n.startsWith('P3')) return 'priority-p3';
  }
  return '';
}

function priorityLabel(labels) {
  if (!labels) return '';
  for (const l of labels) {
    const n = l.name || l;
    if (n.startsWith('P0') || n.startsWith('P1') || n.startsWith('P2') || n.startsWith('P3'))
      return `<span class="${priorityClass(labels)}">[${n}]</span>`;
  }
  return '';
}

function groupBy(arr, keyFn) {
  const m = {};
  for (const item of arr) {
    const k = keyFn(item);
    (m[k] = m[k] || []).push(item);
  }
  return m;
}

function issueUrl(item) {
  return item.url || '#';
}

function repoLink(name) {
  return `<a href="https://github.com/sil-ai/${name}" target="_blank" class="font-medium text-accent hover:text-white transition-colors">${name}</a>`;
}

function escHtml(s) {
  if (!s) return '';
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// Cache with stale-while-revalidate
const cache = {};
let fetchGen = 0;

async function fetchCached(url, onData) {
  const gen = ++fetchGen;
  const cached = cache[url];
  let showedCached = false;
  if (cached) {
    onData(cached.data, true);
    showedCached = true;
    $('#refreshing').classList.remove('hidden');
  }
  if (!showedCached) showLoading();
  const fresh = await fetchJson(url);
  cache[url] = { data: fresh, time: Date.now() };
  hideLoading();
  $('#refreshing').classList.add('hidden');
  if (gen !== fetchGen) return;
  if (!cached || JSON.stringify(fresh) !== JSON.stringify(cached.data)) {
    onData(fresh, false);
  }
}

function showLoading() { loading.classList.remove('hidden'); content.innerHTML = ''; }
function hideLoading() { loading.classList.add('hidden'); }

// --- Global date range ---

let rangeEnd = new Date();
let rangeDays = 7;
let rangeStart = new Date(rangeEnd.getTime() - rangeDays * 86400000);

function dateStr(d) { return d.toISOString().slice(0, 10); }

function updateRangeLabel() {
  const label = $('#range-label');
  if (label) label.textContent = `${dateStr(rangeStart)} – ${dateStr(rangeEnd)}`;
  const nextBtn = $('#range-next');
  if (nextBtn) {
    const isLatest = dateStr(rangeEnd) === dateStr(new Date());
    nextBtn.classList.toggle('opacity-30', isLatest);
    nextBtn.classList.toggle('cursor-not-allowed', isLatest);
    nextBtn.disabled = isLatest;
  }
}

function rangeParams() {
  return `?start=${dateStr(rangeStart)}&end=${dateStr(rangeEnd)}`;
}

// --- Summary ---

function renderSummary(data) {
  let html = `<h2 class="text-2xl font-bold mb-6">Summary</h2>`;

  const commitRepos = Object.keys(data.commits_by_repo || {});
  if (commitRepos.length) {
    html += `<div class="bg-panel rounded-xl p-5 mb-6 border border-border">
      <h3 class="text-lg font-semibold mb-3">Recent Changes</h3>`;
    for (const repo of commitRepos) {
      const commits = data.commits_by_repo[repo];
      const authors = [...new Set(commits.map(c => c.author))];
      const summaryId = `summary-${repo.replace(/[^a-zA-Z0-9]/g, '-')}`;
      html += `<div class="mb-3">
        ${repoLink(repo)}
        <span class="text-gray-500 text-sm">(${commits.length} commits)</span>
        <span class="text-gray-400 text-sm ml-2">${authors.join(', ')}</span>
        <div id="${summaryId}" class="ml-1 mt-1 mb-1 text-sm text-gray-300 border-l-2 border-accent/30 pl-3 hidden"></div>`;
      const commitsId = `commits-${repo.replace(/[^a-zA-Z0-9]/g, '-')}`;
      html += `<div id="${commitsId}" class="hidden">
        <ul class="ml-5 mt-1 text-sm text-gray-300 list-disc">`;
      const commitLink = (c) => `<a href="https://github.com/sil-ai/${repo}/commit/${c.sha}" target="_blank" class="text-gray-500 hover:text-accent font-mono text-xs ml-1">${c.sha}</a>`;
      const commitAuthor = (c) => `<span class="text-gray-500 text-xs ml-1">${escHtml(c.author)}</span>`;
      for (const c of commits) {
        html += `<li>${escHtml(c.message)}${commitLink(c)}${commitAuthor(c)}</li>`;
      }
      html += `</ul></div>`;
      html += `<a href="#" class="text-accent hover:underline text-xs ml-1" onclick="event.preventDefault(); const el = document.getElementById('${commitsId}'); el.classList.toggle('hidden'); this.textContent = el.classList.contains('hidden') ? 'show commits' : 'hide commits'">show commits</a>`;
      html += `</div>`;
    }
    html += `</div>`;
  }

  html += renderIssueSection('Issues Closed', data.issues_closed, 'closedAt');
  html += renderIssueSection('Issues Opened', data.issues_opened, 'createdAt');

  html += `<div class="bg-panel rounded-xl p-5 mb-6 border border-border">
    <h3 class="text-lg font-semibold mb-3">PRs Merged (${data.prs_merged.length})</h3>`;
  if (data.prs_merged.length === 0) {
    html += `<p class="text-gray-500">None in this period</p>`;
  } else {
    const prsByRepo = groupBy(data.prs_merged, i => repoName(i.repository));
    for (const [repo, prs] of Object.entries(prsByRepo)) {
      html += `<div class="mb-2">${repoLink(repo)}<ul class="ml-5 text-sm list-disc">`;
      for (const pr of prs) {
        html += `<li>${escHtml(pr.title)} <span class="text-gray-500">@${pr.author?.login || 'unknown'}</span></li>`;
      }
      html += `</ul></div>`;
    }
  }
  html += `</div>`;

  content.innerHTML = html;

  // Async-fetch AI summaries for each repo's commits
  fetchCommitSummaries(data);
}

// AI commit summaries cache
const summaryCache = {};

async function fetchCommitSummaries(data) {
  const commitRepos = Object.keys(data.commits_by_repo || {});
  if (!commitRepos.length) return;

  // Build merged PRs lookup by repo
  const prsByRepo = {};
  for (const pr of (data.prs_merged || [])) {
    const repo = repoName(pr.repository);
    (prsByRepo[repo] = prsByRepo[repo] || []).push({
      title: pr.title,
      author: pr.author?.login || '?',
    });
  }

  // Build request payload
  const repos = commitRepos.map(repo => ({
    repo,
    commits: data.commits_by_repo[repo],
    merged_prs: prsByRepo[repo] || [],
  }));

  // Check cache - build a key from the data
  const cacheKey = JSON.stringify(repos.map(r => r.repo + ':' + r.commits.length));
  if (summaryCache[cacheKey]) {
    injectSummaries(summaryCache[cacheKey]);
    return;
  }

  // Show loading indicators
  for (const repo of commitRepos) {
    const el = document.getElementById(`summary-${repo.replace(/[^a-zA-Z0-9]/g, '-')}`);
    if (el) {
      el.innerHTML = '<span class="text-gray-500 text-xs">Generating summary...</span>';
      el.classList.remove('hidden');
    }
  }

  try {
    const resp = await fetch('/api/summarize-commits', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repos }),
    });
    if (!resp.ok) {
      // Silently hide on error (e.g. no API key)
      for (const repo of commitRepos) {
        const el = document.getElementById(`summary-${repo.replace(/[^a-zA-Z0-9]/g, '-')}`);
        if (el) el.classList.add('hidden');
      }
      return;
    }
    const result = await resp.json();
    const summaries = result.summaries || {};
    summaryCache[cacheKey] = summaries;
    injectSummaries(summaries);
  } catch {
    // Silently fail - summaries are a nice-to-have
    for (const repo of commitRepos) {
      const el = document.getElementById(`summary-${repo.replace(/[^a-zA-Z0-9]/g, '-')}`);
      if (el) el.classList.add('hidden');
    }
  }
}

function renderSummaryHtml(summary) {
  const lines = summary.split('\n').filter(l => l.trim());
  let html = '';
  for (const line of lines) {
    const isNested = /^\s{2,}[-•*]/.test(line);
    const text = line.replace(/^\s*[-•*]\s*/, '');
    if (isNested) {
      html += `<div class="ml-4 text-gray-400">– ${escHtml(text)}</div>`;
    } else {
      html += `<div class="font-medium text-gray-200">• ${escHtml(text)}</div>`;
    }
  }
  return html;
}

function injectSummaries(summaries) {
  for (const [repo, summary] of Object.entries(summaries)) {
    const el = document.getElementById(`summary-${repo.replace(/[^a-zA-Z0-9]/g, '-')}`);
    if (el && summary) {
      el.innerHTML = renderSummaryHtml(summary);
      el.classList.remove('hidden');
    }
  }
}

async function loadSummary() {
  updateRangeLabel();
  await fetchCached('/api/weekly' + rangeParams(), (data) => renderSummary(data));
}

function renderIssueSection(title, issues, dateField) {
  let html = `<div class="bg-panel rounded-xl p-5 mb-6 border border-border">
    <h3 class="text-lg font-semibold mb-3">${title} (${issues.length})</h3>`;
  if (issues.length === 0) {
    html += `<p class="text-gray-500">None in this period</p>`;
  } else {
    const byRepo = groupBy(issues, i => repoName(i.repository));
    for (const [repo, items] of Object.entries(byRepo)) {
      html += `<div class="mb-2">${repoLink(repo)}<ul class="ml-5 text-sm list-disc">`;
      for (const item of items) {
        html += `<li>${escHtml(item.title)} ${priorityLabel(item.labels)} <span class="text-gray-500">${assigneeStr(item.assignees)}</span></li>`;
      }
      html += `</ul></div>`;
    }
  }
  html += `</div>`;
  return html;
}

// --- Overdue ---

async function loadOverdue() {
  await fetchCached('/api/overdue', (data) => {
    let html = `<h2 class="text-2xl font-bold mb-6">Overdue & Stale Items</h2>`;
    html += renderAgingSection('P0-critical (open &gt; 7 days)', data.aging_p0, 'priority-p0');
    html += renderAgingSection('P1-high (open &gt; 7 days)', data.aging_p1, 'priority-p1');

    html += `<div class="bg-panel rounded-xl p-5 mb-6 border border-border">
      <h3 class="text-lg font-semibold mb-3">Stale Issues (no activity &gt; 30 days) &mdash; ${data.stale.length}</h3>`;
    if (data.stale.length === 0) {
      html += `<p class="text-gray-500">None</p>`;
    } else {
      const byRepo = groupBy(data.stale, i => repoName(i.repository));
      for (const [repo, items] of Object.entries(byRepo)) {
        html += `<div class="mb-2">${repoLink(repo)} <span class="text-gray-500">(${items.length})</span><ul class="ml-5 text-sm list-disc">`;
        for (const item of items) {
          html += `<li><a href="${issueUrl(item)}" target="_blank" class="hover:text-accent">${escHtml(item.title)}</a>
            <span class="text-gray-500">last updated ${fmtDate(item.updatedAt)} (${daysAgo(item.updatedAt)}d ago)</span>
            ${assigneeStr(item.assignees)}</li>`;
        }
        html += `</ul></div>`;
      }
    }
    html += `</div>`;
    content.innerHTML = html;
  });
}

function renderAgingSection(title, items, cls) {
  let html = `<div class="bg-panel rounded-xl p-5 mb-6 border border-border">
    <h3 class="text-lg font-semibold mb-3 ${cls}">${title} &mdash; ${items.length}</h3>`;
  if (items.length === 0) {
    html += `<p class="text-gray-500">None</p>`;
  } else {
    for (const item of items) {
      html += `<div class="mb-1 text-sm">
        ${repoLink(repoName(item.repository))}:
        <a href="${issueUrl(item)}" target="_blank" class="hover:text-accent">${escHtml(item.title)}</a>
        <span class="text-gray-500">- open ${daysAgo(item.createdAt)} days ${assigneeStr(item.assignees)}</span>
      </div>`;
    }
  }
  html += `</div>`;
  return html;
}

// --- Priorities ---

async function loadPriorities() {
  await fetchCached('/api/priorities', (data) => {
    let html = `<h2 class="text-2xl font-bold mb-6">P0 & P1 Priorities</h2>`;
    html += renderPriorityGroup('P0-critical', data.p0, 'priority-p0');
    html += renderPriorityGroup('P1-high', data.p1, 'priority-p1');
    content.innerHTML = html;
  });
}

function renderPriorityGroup(label, items, cls) {
  let html = `<div class="bg-panel rounded-xl p-5 mb-6 border border-border">
    <h3 class="text-lg font-semibold mb-3 ${cls}">${label} (${items.length})</h3>`;
  if (items.length === 0) {
    html += `<p class="text-gray-500">No open issues</p>`;
  } else {
    const byRepo = groupBy(items, i => repoName(i.repository));
    for (const [repo, issues] of Object.entries(byRepo)) {
      html += `<div class="mb-3">${repoLink(repo)}
        <table class="w-full mt-1 text-sm"><tbody>`;
      for (const item of issues) {
        html += `<tr class="border-t border-border">
          <td class="py-1"><a href="${issueUrl(item)}" target="_blank" class="hover:text-accent">${escHtml(item.title)}</a></td>
          <td class="py-1 text-gray-500 text-right w-24">${daysAgo(item.createdAt)}d old</td>
          <td class="py-1 text-gray-400 text-right w-32">${assigneeStr(item.assignees)}</td>
        </tr>`;
      }
      html += `</tbody></table></div>`;
    }
  }
  html += `</div>`;
  return html;
}

// --- PR Status ---

async function loadPrStatus() {
  await fetchCached('/api/pr-status', (data) => {
    const prs = data.prs;
    let html = `<h2 class="text-2xl font-bold mb-6">Open PRs Across Org (${prs.length})</h2>`;

    if (prs.length === 0) {
      html += `<p class="text-gray-500">No open PRs</p>`;
      content.innerHTML = html;
      return;
    }

    const byRepo = groupBy(prs, i => repoName(i.repository));
    const sortedRepos = Object.entries(byRepo).sort((a, b) => b[1].length - a[1].length);

    for (const [repo, repoPrs] of sortedRepos) {
      html += `<div class="bg-panel rounded-xl p-5 mb-4 border border-border">
        <h3 class="text-lg font-semibold mb-3">${repoLink(repo)} <span class="text-gray-500 text-sm">(${repoPrs.length})</span></h3>
        <table class="w-full text-sm"><tbody>`;
      for (const pr of repoPrs) {
        const age = daysAgo(pr.createdAt);
        const ageColor = age > 14 ? 'text-red-400' : age > 7 ? 'text-yellow-400' : 'text-gray-500';
        const draft = pr.isDraft ? '<span class="text-gray-500 bg-white/5 rounded px-1.5 py-0.5 text-xs ml-1">draft</span>' : '';

        const reviewBadges = (pr.reviews || []).map(r => {
          const colors = { 'APPROVED': 'text-green-400', 'CHANGES_REQUESTED': 'text-red-400', 'COMMENTED': 'text-blue-400', 'DISMISSED': 'text-gray-500' };
          const icons = { 'APPROVED': 'ok', 'CHANGES_REQUESTED': 'chg', 'COMMENTED': 'cmt', 'DISMISSED': 'dis' };
          const cls = colors[r.state] || 'text-gray-400';
          const icon = icons[r.state] || r.state;
          return `<span class="${cls} text-xs" title="${r.state}">@${r.user} <span class="opacity-60">${icon}</span></span>`;
        }).join(' ');

        const waiting = (pr.requested_reviewers || []).map(u =>
          `<span class="text-yellow-400 text-xs" title="awaiting review">@${u} <span class="opacity-60">pending</span></span>`
        ).join(' ');

        const reviewCol = [reviewBadges, waiting].filter(Boolean).join(' ') || '<span class="text-gray-600 text-xs">no reviewers</span>';

        html += `<tr class="border-t border-border">
          <td class="py-1.5"><a href="${issueUrl(pr)}" target="_blank" class="hover:text-accent">${escHtml(pr.title)}</a>${draft}</td>
          <td class="py-1.5 text-gray-400 text-right w-28">@${pr.author?.login || '?'}</td>
          <td class="py-1.5 text-right">${reviewCol}</td>
          <td class="py-1.5 ${ageColor} text-right w-16">${age}d</td>
        </tr>`;
      }
      html += `</tbody></table></div>`;
    }
    content.innerHTML = html;
  });
}

// --- Repo Status ---

const projects = {
  'AQuA': ['aqua-api', 'aqua-assessments', 'aqua-django-app', 'attention-word-alignments', 'nllb-word-alignment-from-attention'],
  'Aero': ['aero-api', 'aero-django-app', 'tts-finetuning', 'coqui-mms', 'asr-finetuning', 'SAM-audio-isolation', 'audio-preprocessing'],
  'FaithBridge': ['faithbridge-obt-django-app'],
  'Alpha2': ['madlad-finetuning', 'T5Gemma-finetuning', 'translator', 'translation-tts-app'],
  'GMO Copilot': ['gmo-ai-copilot'],
  'Infra': ['observability-library', 'observability-service', 'playwright-tests', 'shared-skills'],
};
let activeProject = null;

async function loadRepoStatus() {
  await fetchCached('/api/repo-summaries', (summaries) => {
    summaries.sort((a, b) => (b.last_commit || '').localeCompare(a.last_commit || ''));
    renderRepoCards(summaries);
  });
}

function renderRepoCards(summaries) {
  const filtered = activeProject
    ? summaries.filter(r => projects[activeProject]?.includes(r.name))
    : summaries;

  let html = `<h2 class="text-2xl font-bold mb-4">Repo Status</h2>
    <div class="flex flex-wrap gap-2 mb-6">
      <button class="project-btn px-3 py-1.5 rounded-lg text-sm font-medium transition ${!activeProject ? 'bg-accent/90 text-white' : 'bg-panel border border-border text-muted hover:text-gray-200 hover:border-accent/30'}" data-project="">All</button>
      ${Object.keys(projects).map(p => `<button class="project-btn px-3 py-1.5 rounded-lg text-sm font-medium transition ${activeProject === p ? 'bg-accent/90 text-white' : 'bg-panel border border-border text-muted hover:text-gray-200 hover:border-accent/30'}" data-project="${p}">${p} <span class="text-xs opacity-60">${projects[p].length}</span></button>`).join('')}
    </div>
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">`;

  const maxWeek = Math.max(1, ...filtered.map(r => Math.max(...(r.week_commits || [0]))));

  for (const repo of filtered) {
    const hasP0 = repo.p0 > 0;
    const hasP1 = repo.p1 > 0;
    const border = hasP0 ? 'border-red-500/40' : hasP1 ? 'border-yellow-500/25' : 'border-border';
    const lastCommit = repo.last_commit ? timeAgo(repo.last_commit) : '';

    let issueList = '';
    for (const i of (repo.top_issues || [])) {
      const pcls = priorityClass(i.labels?.map(n => ({name: n})));
      const plbl = i.labels?.find(n => n.match(/^P[0-3]/));
      const badge = plbl ? `<span class="${pcls} text-xs">${plbl}</span> ` : '';
      issueList += `<div class="truncate text-xs text-gray-300">${badge}<a href="${i.url}" target="_blank" class="hover:text-accent" onclick="event.stopPropagation()">${escHtml(i.title)}</a></div>`;
    }

    let prList = '';
    for (const p of (repo.top_prs || [])) {
      const draft = p.isDraft ? '<span class="text-gray-500 text-xs">[draft]</span> ' : '';
      prList += `<div class="truncate text-xs text-gray-300">${draft}<a href="${p.url}" target="_blank" class="hover:text-accent" onclick="event.stopPropagation()">#${p.number}</a> ${escHtml(p.title)} <span class="text-gray-500">@${p.author}</span></div>`;
    }

    html += `<div class="bg-panel rounded-xl p-4 border ${border} cursor-pointer hover:border-accent/50 hover:shadow-lg hover:shadow-black/10 transition-all duration-200 repo-card" data-repo="${repo.name}">
      <div class="flex items-center justify-between mb-2">
        <div class="font-semibold text-white truncate">${repo.name}</div>
        ${lastCommit ? `<span class="text-xs text-gray-500 whitespace-nowrap ml-2">${lastCommit}</span>` : ''}
      </div>
      <div class="flex items-center gap-4 text-sm mb-2">
        <span class="text-gray-400">Issues <span class="text-white">${repo.issues}</span></span>
        <span class="text-gray-400">PRs <span class="text-white">${repo.prs}</span></span>
        ${hasP0 ? `<span class="priority-p0 text-xs">P0: ${repo.p0}</span>` : ''}
        ${hasP1 ? `<span class="priority-p1 text-xs">P1: ${repo.p1}</span>` : ''}
        <span class="flex items-end gap-px ml-auto h-4" title="Commits: last 4 weeks">${
          (repo.week_commits || [0,0,0,0]).slice().reverse().map(c => {
            const h = c === 0 ? 2 : Math.max(4, Math.round((c / maxWeek) * 16));
            const color = c === 0 ? 'bg-white/5' : 'bg-accent/60';
            return `<span class="${color} rounded-sm" style="width:4px;height:${h}px"></span>`;
          }).join('')
        }</span>
      </div>
      ${issueList ? `<div class="border-t border-border pt-2 mt-1 space-y-0.5">${issueList}</div>` : ''}
      ${prList ? `<div class="border-t border-border pt-2 mt-1 space-y-0.5">${prList}</div>` : ''}
    </div>`;
  }

  html += `</div>`;
  content.innerHTML = html;

  $$('.repo-card').forEach(card => {
    card.addEventListener('click', () => openRepoModal(card.dataset.repo));
  });

  $$('.project-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      activeProject = btn.dataset.project || null;
      renderRepoCards(summaries);
    });
  });
}

async function openRepoModal(repo) {
  const modal = $('#modal');
  const title = $('#modal-title');
  const body = $('#modal-body');
  const url = `/api/repo-status/${repo}${rangeParams()}`;

  title.innerHTML = repoLink(repo);
  modal.classList.remove('hidden');

  const cached = cache[url];
  if (cached) {
    renderRepoModal(cached.data);
    // Show refreshing indicator and fetch fresh data
    $('#refreshing').classList.remove('hidden');
    try {
      const fresh = await fetchJson(url);
      cache[url] = { data: fresh, time: Date.now() };
      $('#refreshing').classList.add('hidden');
      if (JSON.stringify(fresh) !== JSON.stringify(cached.data)) {
        renderRepoModal(fresh);
      }
    } catch { $('#refreshing').classList.add('hidden'); }
  } else {
    body.innerHTML = '<div class="flex items-center gap-3 py-8 justify-center"><div class="spinner"></div><span class="text-gray-400">Loading...</span></div>';
    const data = await fetchJson(url);
    cache[url] = { data: data, time: Date.now() };
    renderRepoModal(data);
  }
}

function renderRepoModal(data) {
  const body = $('#modal-body');
  let html = '';

  // Recent Changes first
  const branches = Object.keys(data.branch_commits || {});
  if (branches.length) {
    html += `<div class="mb-6">
      <h4 class="font-semibold mb-3">Recent Changes</h4>
      <div id="modal-commit-summary" class="mb-3 text-sm text-gray-300 border-l-2 border-accent/30 pl-3 hidden"></div>
      <a href="#" class="text-accent hover:underline text-xs" onclick="event.preventDefault(); const el = document.getElementById('modal-commits-detail'); el.classList.toggle('hidden'); this.textContent = el.classList.contains('hidden') ? 'show commits' : 'hide commits'">show commits</a>
      <div id="modal-commits-detail" class="hidden">`;
    for (const branch of branches) {
      const commits = data.branch_commits[branch];
      html += `<div class="mb-3 mt-2">
        <span class="text-sm font-mono bg-white/5 text-gray-300 rounded px-2 py-0.5">${escHtml(branch)}</span>
        <ul class="ml-5 mt-1 text-sm list-disc space-y-0.5">`;
      for (const c of commits) {
        html += `<li>
          <a href="https://github.com/sil-ai/${data.repo}/commit/${c.sha}" target="_blank" class="text-gray-500 hover:text-accent font-mono text-xs">${c.sha}</a>
          ${escHtml(c.message)}
          <span class="text-gray-500 text-xs">${c.author} - ${fmtDate(c.date)}</span>
        </li>`;
      }
      html += `</ul></div>`;
    }
    html += `</div></div>`;
  }

  // Open PRs
  html += `<div class="mb-6">
    <h4 class="font-semibold mb-3">Open PRs (${data.prs.length})</h4>`;
  if (data.prs.length === 0) {
    html += `<p class="text-gray-500">None</p>`;
  } else {
    html += `<table class="w-full text-sm"><tbody>`;
    for (const pr of data.prs) {
      html += `<tr class="border-t border-border">
        <td class="py-1"><a href="${issueUrl(pr)}" target="_blank" class="hover:text-accent">#${pr.number} ${escHtml(pr.title)}</a>${pr.isDraft ? ' <span class="text-gray-500 bg-white/5 rounded px-1.5 py-0.5 text-xs">draft</span>' : ''}</td>
        <td class="py-1 text-gray-400 text-right">@${pr.author?.login || '?'}</td>
        <td class="py-1 text-gray-500 text-right w-24">${daysAgo(pr.createdAt)}d</td>
      </tr>`;
    }
    html += `</tbody></table>`;
  }
  html += `</div>`;

  // Open Issues
  const byPriority = { 'P0-critical': [], 'P1-high': [], 'P2-important': [], 'P3-strategic': [], 'No priority': [] };
  for (const issue of data.issues) {
    let found = false;
    for (const l of (issue.labels || [])) {
      const n = l.name || l;
      if (byPriority[n] !== undefined) { byPriority[n].push(issue); found = true; break; }
    }
    if (!found) byPriority['No priority'].push(issue);
  }

  html += `<div class="mb-6">
    <h4 class="font-semibold mb-3">Open Issues (${data.issues.length})</h4>`;
  for (const [pri, issues] of Object.entries(byPriority)) {
    if (!issues.length) continue;
    const cls = pri.startsWith('P0') ? 'priority-p0' : pri.startsWith('P1') ? 'priority-p1' : pri.startsWith('P2') ? 'priority-p2' : '';
    html += `<div class="mb-2"><span class="${cls} text-sm">${pri} (${issues.length})</span><ul class="ml-5 text-sm list-disc">`;
    for (const i of issues) {
      const prBadges = (i.linked_prs || []).map(p =>
        `<a href="${p.url}" target="_blank" class="inline-flex items-center gap-0.5 text-xs bg-green-900/40 text-green-400 rounded px-1.5 py-0.5 hover:bg-green-900/60" title="${escHtml(p.title)}">PR #${p.number}</a>`
      ).join(' ');
      html += `<li><a href="${issueUrl(i)}" target="_blank" class="hover:text-accent">${escHtml(i.title)}</a> ${prBadges} <span class="text-gray-500">${assigneeStr(i.assignees)} - ${daysAgo(i.createdAt)}d old</span></li>`;
    }
    html += `</ul></div>`;
  }
  html += `</div>`;

  // Milestones
  if (data.milestones && data.milestones.length) {
    html += `<div class="mb-6">
      <h4 class="font-semibold mb-3">Milestones</h4>
      <table class="w-full text-sm"><thead><tr class="text-gray-500 border-b border-border">
        <th class="text-left py-1">Milestone</th><th class="text-right py-1">Due</th><th class="text-right py-1">Open</th><th class="text-right py-1">Closed</th>
      </tr></thead><tbody>`;
    for (const m of data.milestones) {
      const overdue = m.due_on && new Date(m.due_on) < new Date() ? 'text-red-400' : '';
      html += `<tr class="border-t border-border">
        <td class="py-1">${escHtml(m.title)}</td>
        <td class="py-1 text-right ${overdue}">${m.due_on ? fmtDate(m.due_on) : 'No date'}</td>
        <td class="py-1 text-right">${m.open_issues}</td>
        <td class="py-1 text-right text-gray-500">${m.closed_issues}</td>
      </tr>`;
    }
    html += `</tbody></table></div>`;
  }

  // Recently Closed
  html += `<div class="mb-6">
    <h4 class="font-semibold mb-3">Recently Closed (14 days)</h4>`;
  if (data.recent_closed.length === 0) {
    html += `<p class="text-gray-500">None</p>`;
  } else {
    html += `<ul class="text-sm list-disc ml-5">`;
    for (const i of data.recent_closed) {
      html += `<li><a href="${issueUrl(i)}" target="_blank" class="hover:text-accent">${escHtml(i.title)}</a> <span class="text-gray-500">${fmtDate(i.closedAt)}</span></li>`;
    }
    html += `</ul>`;
  }
  html += `</div>`;

  body.innerHTML = html;

  // Fetch AI summary for modal commits (with client-side cache)
  if (branches.length) {
    const allCommits = branches.flatMap(b => data.branch_commits[b] || []);
    if (allCommits.length) {
      const el = document.getElementById('modal-commit-summary');
      const cacheKey = 'modal:' + data.repo + ':' + allCommits.map(c => c.sha).join(',');
      if (el) {
        if (summaryCache[cacheKey]) {
          el.innerHTML = renderSummaryHtml(summaryCache[cacheKey]);
          el.classList.remove('hidden');
        } else {
          el.innerHTML = '<span class="text-gray-500 text-xs">Generating summary...</span>';
          el.classList.remove('hidden');
          fetch('/api/summarize-commits', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ repos: [{ repo: data.repo, commits: allCommits, merged_prs: [] }] }),
          }).then(r => r.ok ? r.json() : null).then(result => {
            const summary = result?.summaries?.[data.repo];
            if (summary && el) {
              summaryCache[cacheKey] = summary;
              el.innerHTML = renderSummaryHtml(summary);
            } else if (el) {
              el.classList.add('hidden');
            }
          }).catch(() => { if (el) el.classList.add('hidden'); });
        }
      }
    }
  }
}

// --- My Tasks ---

async function loadMyTasks() {
  if (!orgMembers.length) orgMembers = await fetchJson('/api/org-members');
  const saved = localStorage.getItem('my-tasks-user') || '';

  let html = `<h2 class="text-2xl font-bold mb-4">My Tasks</h2>
    <div class="mb-6">
      <select id="member-select" class="bg-panel border border-border text-gray-200 rounded-lg px-4 py-2 w-72">
        <option value="">Select a team member...</option>
        ${orgMembers.map(m => `<option value="${m}" ${m === saved ? 'selected' : ''}>${m}</option>`).join('')}
      </select>
      <button id="member-load-btn" class="ml-2 bg-accent/90 text-white px-4 py-2 rounded-lg hover:bg-accent transition-colors">Load</button>
    </div>
    <div id="member-content"></div>`;
  content.innerHTML = html;

  const loadUser = async () => {
    const user = $('#member-select').value;
    if (!user) return;
    localStorage.setItem('my-tasks-user', user);
    const url = `/api/my-tasks/${user}`;
    const cached = cache[url];
    if (!cached) {
      $('#member-content').innerHTML = '<div class="flex items-center gap-3 py-8"><div class="spinner"></div><span class="text-gray-400">Loading...</span></div>';
    }
    await fetchCached(url, (data) => renderMyTasksData(user, data));
  };

  $('#member-load-btn').addEventListener('click', loadUser);

  if (saved) loadUser();
}

function renderMyTasksData(user, data) {
  const el = $('#member-content');
  let html = `<h3 class="text-xl font-semibold mb-4">@${user}</h3>`;

  html += `<div class="bg-panel rounded-xl p-5 mb-6 border border-border">
    <h4 class="font-semibold mb-3">Assigned Issues (${data.issues.length})</h4>`;
  if (data.issues.length === 0) {
    html += `<p class="text-gray-500">No open issues assigned</p>`;
  } else {
    const byRepo = groupBy(data.issues, i => repoName(i.repository));
    for (const [repo, issues] of Object.entries(byRepo)) {
      html += `<div class="mb-3">${repoLink(repo)}
        <ul class="ml-5 text-sm list-disc">`;
      for (const i of issues) {
        html += `<li><a href="${issueUrl(i)}" target="_blank" class="hover:text-accent">${escHtml(i.title)}</a>
          ${priorityLabel(i.labels)}
          <span class="text-gray-500">${daysAgo(i.createdAt)}d old</span></li>`;
      }
      html += `</ul></div>`;
    }
  }
  html += `</div>`;

  html += `<div class="bg-panel rounded-xl p-5 mb-6 border border-border">
    <h4 class="font-semibold mb-3">Open PRs (${data.prs.length})</h4>`;
  if (data.prs.length === 0) {
    html += `<p class="text-gray-500">No open PRs</p>`;
  } else {
    const byRepo = groupBy(data.prs, i => repoName(i.repository));
    for (const [repo, prs] of Object.entries(byRepo)) {
      html += `<div class="mb-2">${repoLink(repo)}<ul class="ml-5 text-sm list-disc">`;
      for (const pr of prs) {
        html += `<li><a href="${issueUrl(pr)}" target="_blank" class="hover:text-accent">${escHtml(pr.title)}</a>
          <span class="text-gray-500">${daysAgo(pr.createdAt)}d old</span></li>`;
      }
      html += `</ul></div>`;
    }
  }
  html += `</div>`;

  el.innerHTML = html;
}

// --- Tab navigation ---

const tabHandlers = {
  'summary': loadSummary,
  'overdue': loadOverdue,
  'priorities': loadPriorities,
  'pr-status': loadPrStatus,
  'repo-status': loadRepoStatus,
  'my-tasks': loadMyTasks,
};

function activateTab(tab) {
  $$('.tab-btn').forEach(b => b.classList.remove('active'));
  const btn = document.querySelector(`.tab-btn[data-tab="${tab}"]`);
  if (btn) btn.classList.add('active');
  tabHandlers[tab]();
}

$$('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;
    history.pushState(null, '', `#${tab}`);
    activateTab(tab);
  });
});

// Modal close handlers
function closeModal() { $('#modal').classList.add('hidden'); }
$('#modal-close').addEventListener('click', closeModal);
$('#modal').addEventListener('click', (e) => { if (e.target === $('#modal')) closeModal(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });

window.addEventListener('popstate', () => {
  const tab = location.hash.slice(1) || 'summary';
  if (tabHandlers[tab]) activateTab(tab);
});

// --- Date range controls ---
$('#range-prev').addEventListener('click', () => {
  rangeEnd = new Date(rangeStart.getTime() - 86400000);
  rangeStart = new Date(rangeEnd.getTime() - rangeDays * 86400000);
  onRangeChange();
});
$('#range-next').addEventListener('click', () => {
  if ($('#range-next').disabled) return;
  rangeStart = new Date(rangeEnd.getTime() + 86400000);
  rangeEnd = new Date(rangeStart.getTime() + rangeDays * 86400000);
  const today = new Date();
  if (rangeEnd > today) rangeEnd = today;
  onRangeChange();
});
$('#range-period').addEventListener('change', (e) => {
  rangeDays = parseInt(e.target.value);
  rangeEnd = new Date();
  rangeStart = new Date(rangeEnd.getTime() - rangeDays * 86400000);
  onRangeChange();
});

function onRangeChange() {
  updateRangeLabel();
  // Re-load the current tab to reflect the new date range
  const activeTab = document.querySelector('.tab-btn.active')?.dataset.tab || 'summary';
  if (tabHandlers[activeTab]) tabHandlers[activeTab]();
}

// Init
$('#timestamp').textContent = new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
updateRangeLabel();
const initTab = location.hash.slice(1) || 'summary';
// Support old #weekly URLs
activateTab(tabHandlers[initTab] ? initTab : 'summary');
