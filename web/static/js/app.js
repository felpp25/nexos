/* =============================================================================
   NEXOS - front-end (vanilla JS, sem build)
   ========================================================================== */

const state = {
  view: 'chat',
  agents: [],
  health: null,
  models: [],
  chatAgentId: null,
  conversationId: null,
  streaming: false,
  filter: 'active',
  search: '',
  pendingFiles: [],
  masterDirty: false,
  setup: null,
  pulling: false,
};

/* ------------------------------------------------------------------- utils */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const icon = (name, cls = '') => `<svg class="${cls}"><use href="#i-${name}"/></svg>`;

// Atomo animado do indicador de "pensando".
// Inline (e nao no sprite com <use>) porque o <use> cria shadow DOM.
// A rotacao usa <animateTransform> do proprio SVG, e nao CSS: assim o centro de
// giro ("0 0", o nucleo) e explicito, sem depender de como o navegador resolve
// transform-origin/transform-box dentro de SVG.
// dir: 1 gira no sentido horario, -1 no anti-horario (orbitas cruzando em
// direcoes diferentes dao a sensacao de volume, como um atomo de verdade)
const ORBITS = [
  { from: 0, dur: 2.2, dir: 1, opacity: 0.85, r: 1.9 },
  { from: 60, dur: 3.0, dir: -1, opacity: 0.65, r: 1.6 },
  { from: 120, dur: 3.8, dir: 1, opacity: 0.5, r: 1.4 },
];

function atomSvg() {
  // O indicador comunica um estado (o app esta trabalhando), entao o giro roda
  // sempre - inclusive com "animacoes desligadas" no Windows, onde o app ficaria
  // parecendo travado. Com prefers-reduced-motion cortamos so o movimento
  // acessorio: a pulsacao do nucleo e o piscar do rotulo.
  const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const orbits = ORBITS.map((o) => {
    const to = o.from + 360 * o.dir;
    return `
      <g transform="rotate(${o.from})">
        <ellipse rx="10" ry="3.9" stroke-width="1.15" opacity="${o.opacity}"/>
        <circle cx="10" cy="0" r="${o.r}" fill="currentColor" stroke="none"/>
        <animateTransform attributeName="transform" type="rotate"
          from="${o.from} 0 0" to="${to} 0 0"
          dur="${o.dur}s" repeatCount="indefinite"/>
      </g>`;
  }).join('');

  const core = reduced
    ? '<circle r="2.8" fill="currentColor" stroke="none"/>'
    : `<circle r="2.8" fill="currentColor" stroke="none">
         <animate attributeName="r" values="2.8;2.2;2.8" dur="1.8s" repeatCount="indefinite"/>
         <animate attributeName="opacity" values="1;0.55;1" dur="1.8s" repeatCount="indefinite"/>
       </circle>`;

  return `<svg class="atom" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
      <g transform="translate(12 12)">${orbits}${core}</g>
    </svg>`;
}

const thinkingHtml = (label = 'pensando') =>
  `<span class="thinking" role="status" aria-live="polite">${atomSvg()}<span class="label">${escapeHtml(label)}</span></span>`;

function escapeHtml(str) {
  return String(str == null ? '' : str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function timeAgo(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (Number.isNaN(diff)) return '';
  if (diff < 60) return 'agora';
  if (diff < 3600) return `${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h`;
  return `${Math.floor(diff / 86400)} d`;
}

function initials(name) {
  const parts = String(name || '?').trim().split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]).join('').toUpperCase() || '?';
}

function toast(title, desc = '', kind = '') {
  const host = $('#toasts');
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.innerHTML = `<div class="title">${escapeHtml(title)}</div>${desc ? `<div class="desc">${escapeHtml(desc)}</div>` : ''}`;
  host.appendChild(el);
  setTimeout(() => {
    el.style.transition = 'opacity 200ms ease';
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 220);
  }, 4200);
}

async function api(path, options = {}) {
  const opts = { ...options };
  if (opts.body && !(opts.body instanceof FormData)) {
    opts.headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    } catch (_) { /* resposta sem json */ }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

/* --------------------------------------------------------------- markdown */
function renderMarkdown(text) {
  const blocks = [];
  let src = String(text || '').replace(/\r\n/g, '\n');

  src = src.replace(/```(\w*)\n?([\s\S]*?)```/g, (_m, lang, code) => {
    blocks.push(`<pre><code data-lang="${escapeHtml(lang)}">${escapeHtml(code.replace(/\n$/, ''))}</code></pre>`);
    return `%%NXBLOCK${blocks.length - 1}%%`;
  });

  const inline = (s) => escapeHtml(s)
    .replace(/`([^`]+)`/g, (_m, c) => `<code>${c}</code>`)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(/\[(\d{1,2})\]/g, '<span class="cite">$1</span>')
    .replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  const lines = src.split('\n');
  const out = [];
  let list = null;
  let table = null;

  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
  const closeTable = () => {
    if (table) {
      out.push('<table>');
      table.forEach((row, i) => {
        const tag = i === 0 ? 'th' : 'td';
        out.push(`<tr>${row.map((c) => `<${tag}>${inline(c)}</${tag}>`).join('')}</tr>`);
      });
      out.push('</table>');
      table = null;
    }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const blockMatch = line.match(/^%%NXBLOCK(\d+)%%$/);
    if (blockMatch) { closeList(); closeTable(); out.push(blocks[Number(blockMatch[1])]); continue; }
    if (!line.trim()) { closeList(); closeTable(); continue; }

    if (/^\|(.+)\|$/.test(line)) {
      const cells = line.slice(1, -1).split('|').map((c) => c.trim());
      if (cells.every((c) => /^:?-{2,}:?$/.test(c))) continue;
      closeList();
      (table = table || []).push(cells);
      continue;
    }
    closeTable();

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) { closeList(); out.push(`<h3>${inline(heading[2])}</h3>`); continue; }

    if (/^>\s?/.test(line)) { closeList(); out.push(`<blockquote>${inline(line.replace(/^>\s?/, ''))}</blockquote>`); continue; }

    const ul = line.match(/^\s*[-*]\s+(.*)$/);
    const ol = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (ul || ol) {
      const want = ul ? 'ul' : 'ol';
      if (list !== want) { closeList(); out.push(`<${want}>`); list = want; }
      out.push(`<li>${inline((ul || ol)[1])}</li>`);
      continue;
    }

    closeList();
    out.push(`<p>${inline(line)}</p>`);
  }
  closeList();
  closeTable();
  return out.join('\n');
}

/* ------------------------------------------------------------------ modal */
function openModal({ title, body, footer, wide = false, onMount }) {
  const host = $('#modalHost');
  host.innerHTML = `
    <div class="modal-backdrop">
      <div class="modal ${wide ? '' : 'modal-sm'}">
        <header>
          <h2>${escapeHtml(title)}</h2>
          <button class="btn btn-ghost btn-icon" data-close style="margin-left:auto">${icon('x')}</button>
        </header>
        <div class="modal-body">${body}</div>
        <footer>${footer || ''}</footer>
      </div>
    </div>`;
  const backdrop = $('.modal-backdrop', host);
  const close = () => { host.innerHTML = ''; document.removeEventListener('keydown', onKey); };
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  document.addEventListener('keydown', onKey);
  backdrop.addEventListener('mousedown', (e) => { if (e.target === backdrop) close(); });
  $$('[data-close]', host).forEach((b) => b.addEventListener('click', close));
  if (onMount) onMount(host, close);
  return close;
}

function confirmModal(title, message, confirmLabel, onConfirm, danger = true) {
  openModal({
    title,
    body: `<p class="muted mb-0">${escapeHtml(message)}</p>`,
    footer: `<button class="btn btn-ghost" data-close>Cancelar</button>
             <button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-confirm>${escapeHtml(confirmLabel)}</button>`,
    onMount: (host, close) => {
      $('[data-confirm]', host).addEventListener('click', async () => { close(); await onConfirm(); });
    },
  });
}

/* ----------------------------------------------------------------- status */
async function loadHealth() {
  try {
    const health = await api('/api/health');
    state.health = health;
    state.models = health.ollama.models || [];

    const online = health.ollama.online;
    $('#dotOllama').className = `dot ${online ? 'on' : 'off'}`;
    $('#statusModel').textContent = online ? health.model : 'offline';
    $('#statusModel').title = online ? `${health.model} @ ${health.ollama.url}` : health.ollama.error || '';

    const emb = health.embeddings;
    $('#dotEmbed').className = `dot ${emb.backend === 'ollama' ? 'on' : 'warn'}`;
    $('#statusEmbed').textContent = emb.backend === 'ollama' ? emb.model : 'basico';
    $('#statusEmbed').title = emb.hint || `Backend ${emb.backend}`;

    $('#statusBase').textContent = `${health.counts.documents} docs`;
    if (!online) toastOnce('ollama-off', 'Ollama offline', 'Inicie o Ollama para conversar com os agentes.', 'error');
  } catch (err) {
    $('#dotOllama').className = 'dot off';
    $('#statusModel').textContent = 'erro';
  }
}

const toastedOnce = new Set();
function toastOnce(key, title, desc, kind) {
  if (toastedOnce.has(key)) return;
  toastedOnce.add(key);
  toast(title, desc, kind);
}

function fillModelSelect(select, current = '') {
  const options = ['<option value="">Padrao do sistema</option>']
    .concat(state.models.map((m) => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`));
  select.innerHTML = options.join('');
  select.value = current || '';
}

/* ----------------------------------------------------------------- agents */
async function loadAgents() {
  const data = await api('/api/agents?status=all');
  state.agents = data.agents;
  $('#navAgentCount').textContent = state.agents.filter((a) => a.status === 'active').length;
  renderAgentSelect();
  renderAgentGrid();
  renderPreviewAgents();
}

function activeAgents() {
  return state.agents.filter((a) => a.status === 'active');
}

function renderAgentSelect() {
  const select = $('#chatAgent');
  const agents = activeAgents();
  if (!agents.length) {
    select.innerHTML = '<option value="">Nenhum agente ativo</option>';
    state.chatAgentId = null;
    renderChatMessages([]);
    renderConversations([]);
    updateChatBadge();
    return;
  }
  if (!state.chatAgentId || !agents.some((a) => a.id === state.chatAgentId)) {
    state.chatAgentId = agents[0].id;
  }
  select.innerHTML = agents
    .map((a) => `<option value="${a.id}">${escapeHtml(a.name)}</option>`)
    .join('');
  select.value = state.chatAgentId;
  updateChatBadge();
}

function updateChatBadge() {
  const agent = state.agents.find((a) => a.id === state.chatAgentId);
  const badge = $('#chatAgentBadge');
  if (!agent) { badge.className = 'badge'; badge.textContent = 'sem agente'; return; }
  if (agent.documents > 0) {
    badge.className = 'badge badge-success';
    badge.textContent = `${agent.documents} doc${agent.documents > 1 ? 's' : ''} - ${agent.chunks} trechos`;
  } else {
    badge.className = 'badge badge-warning';
    badge.textContent = 'sem base de conhecimento';
  }
}

function renderAgentGrid() {
  const grid = $('#agentGrid');
  const term = state.search.trim().toLowerCase();
  let list = state.agents;
  if (state.filter !== 'all') list = list.filter((a) => a.status === state.filter);
  if (term) list = list.filter((a) => `${a.name} ${a.purpose}`.toLowerCase().includes(term));

  if (!list.length) {
    grid.innerHTML = `
      <div class="empty" style="grid-column:1/-1">
        <div class="icon">${icon('bot')}</div>
        <h3>Nenhum agente aqui</h3>
        <p>${state.filter === 'archived' ? 'Voce ainda nao arquivou nenhum agente.' : 'Crie o primeiro agente e envie os documentos da base de conhecimento.'}</p>
        <button class="btn btn-primary" onclick="window.nexos.go('create')">${icon('plus')} Criar agente</button>
      </div>`;
    return;
  }

  grid.innerHTML = list.map((a) => `
    <article class="agent-card ${a.status === 'archived' ? 'archived' : ''}">
      <div class="top">
        <div class="agent-avatar">${escapeHtml(initials(a.name))}</div>
        <div style="min-width:0">
          <h3>${escapeHtml(a.name)}</h3>
          <div class="small subtle">${a.status === 'archived' ? 'arquivado' : 'ativo'} &middot; atualizado ha ${timeAgo(a.updated_at)}</div>
        </div>
        ${a.use_master ? '' : '<span class="badge badge-warning" style="margin-left:auto">prompt proprio</span>'}
      </div>
      <p class="purpose">${escapeHtml(a.purpose || 'Sem proposito definido.')}</p>
      <div class="stats">
        <span>${a.documents} documento${a.documents === 1 ? '' : 's'}</span>
        <span>${a.chunks} trechos</span>
        <span>${escapeHtml(a.model || 'modelo padrao')}</span>
      </div>
      <div class="actions">
        <button class="btn btn-secondary btn-sm" data-edit="${a.id}">${icon('edit')} Editar</button>
        ${a.status === 'active'
          ? `<button class="btn btn-ghost btn-sm" data-archive="${a.id}">${icon('archive')} Arquivar</button>`
          : `<button class="btn btn-ghost btn-sm" data-restore="${a.id}">${icon('restore')} Restaurar</button>`}
        <button class="btn btn-danger btn-sm" data-delete="${a.id}" style="margin-left:auto">${icon('trash')}</button>
      </div>
    </article>`).join('');

  $$('[data-edit]', grid).forEach((b) => b.addEventListener('click', () => openAgentEditor(b.dataset.edit)));
  $$('[data-archive]', grid).forEach((b) => b.addEventListener('click', async () => {
    await api(`/api/agents/${b.dataset.archive}/archive`, { method: 'POST' });
    toast('Agente arquivado', '', 'success');
    await loadAgents();
  }));
  $$('[data-restore]', grid).forEach((b) => b.addEventListener('click', async () => {
    await api(`/api/agents/${b.dataset.restore}/restore`, { method: 'POST' });
    toast('Agente restaurado', '', 'success');
    await loadAgents();
  }));
  $$('[data-delete]', grid).forEach((b) => b.addEventListener('click', () => {
    const agent = state.agents.find((a) => a.id === b.dataset.delete);
    confirmModal(
      'Excluir agente',
      `"${agent.name}" sera removido com todos os documentos, trechos e conversas. Esta acao nao pode ser desfeita.`,
      'Excluir definitivamente',
      async () => {
        await api(`/api/agents/${agent.id}`, { method: 'DELETE' });
        toast('Agente excluido', '', 'success');
        if (state.chatAgentId === agent.id) { state.chatAgentId = null; state.conversationId = null; }
        await loadAgents();
        await loadHealth();
      },
    );
  }));
}

/* ------------------------------------------------------- editor de agente */
function documentRow(doc) {
  const ext = (doc.filename.split('.').pop() || '?').slice(0, 4);
  const status = {
    ready: `<span class="badge badge-success">pronto</span>`,
    processing: `<span class="badge badge-warning">processando</span>`,
    error: `<span class="badge badge-danger">erro</span>`,
  }[doc.status] || '';
  const desc = doc.status === 'error'
    ? `<div class="desc error">${escapeHtml(doc.error || 'falha ao processar')}</div>`
    : `<div class="desc">${formatBytes(doc.size_bytes)} &middot; ${doc.chunks} trechos</div>`;
  return `
    <div class="file-row" data-doc="${doc.id}">
      <div class="ficon">${escapeHtml(ext)}</div>
      <div class="meta"><div class="name">${escapeHtml(doc.filename)}</div>${desc}</div>
      ${status}
      ${doc.status === 'error' ? `<button class="btn btn-ghost btn-icon btn-sm" data-reprocess="${doc.id}" title="Reprocessar">${icon('refresh')}</button>` : ''}
      <button class="btn btn-ghost btn-icon btn-sm" data-deldoc="${doc.id}" title="Remover">${icon('trash')}</button>
    </div>`;
}

async function openAgentEditor(agentId) {
  const agent = await api(`/api/agents/${agentId}`);
  const docs = await api(`/api/agents/${agentId}/documents`);

  const body = `
    <div class="field">
      <label>Nome</label>
      <input class="input" id="eName" value="${escapeHtml(agent.name)}" maxlength="120" />
    </div>
    <div class="field">
      <label>Proposito</label>
      <textarea class="textarea" id="ePurpose">${escapeHtml(agent.purpose)}</textarea>
    </div>
    <div class="field">
      <label>Observacoes</label>
      <textarea class="textarea" id="eObs">${escapeHtml(agent.observations)}</textarea>
    </div>
    <div class="row">
      <div class="field">
        <label>Modelo</label>
        <select class="select" id="eModel"></select>
      </div>
      <div class="field">
        <label>Temperatura</label>
        <input class="input" id="eTemp" type="number" min="0" max="2" step="0.1" value="${agent.temperature}" />
      </div>
      <div class="field">
        <label>Trechos por resposta</label>
        <input class="input" id="eTopK" type="number" min="0" max="20" step="1" value="${agent.top_k}" />
      </div>
    </div>
    <div class="field">
      <label class="switch">
        <input type="checkbox" id="eUseMaster" ${agent.use_master ? 'checked' : ''} /><span class="track"></span>
        <span>Usar o prompt mestre global</span>
      </label>
    </div>
    <div class="field">
      <label>Instrucoes exclusivas</label>
      <textarea class="textarea mono" id="eOverride" placeholder="Opcional">${escapeHtml(agent.prompt_override)}</textarea>
    </div>

    <div class="section-divider"></div>
    <h3 style="font-size:1rem;margin-bottom:4px">Base de conhecimento</h3>
    <p class="small subtle" style="margin:0 0 12px">${docs.documents.length} documento(s) neste agente.</p>
    <div class="dropzone" id="eDrop">
      <div class="icon">${icon('upload')}</div>
      <strong>Adicionar documentos</strong>
      <p>PDF, DOCX, PPTX, TXT, MD, CSV ou imagem</p>
      <input type="file" id="eFiles" multiple class="hidden" />
    </div>
    <div class="file-list" id="eDocs">${docs.documents.map(documentRow).join('')}</div>`;

  openModal({
    title: 'Editar agente',
    wide: true,
    body,
    footer: `<button class="btn btn-ghost" data-close>Cancelar</button>
             <button class="btn btn-primary" data-save>${icon('save')} Salvar alteracoes</button>`,
    onMount: (host, close) => {
      fillModelSelect($('#eModel', host), agent.model);

      const refreshDocs = async () => {
        const fresh = await api(`/api/agents/${agentId}/documents`);
        const list = $('#eDocs', host);
        if (!list) return fresh;
        list.innerHTML = fresh.documents.map(documentRow).join('');
        bindDocActions();
        return fresh;
      };

      const pollDocs = async () => {
        for (let i = 0; i < 60; i += 1) {
          const fresh = await refreshDocs();
          if (!fresh.documents.some((d) => d.status === 'processing')) return;
          await new Promise((r) => setTimeout(r, 1200));
        }
      };

      function bindDocActions() {
        $$('[data-deldoc]', host).forEach((b) => b.addEventListener('click', async () => {
          await api(`/api/documents/${b.dataset.deldoc}`, { method: 'DELETE' });
          toast('Documento removido', '', 'success');
          await refreshDocs();
          await loadAgents();
        }));
        $$('[data-reprocess]', host).forEach((b) => b.addEventListener('click', async () => {
          await api(`/api/documents/${b.dataset.reprocess}/reprocess`, { method: 'POST' });
          await pollDocs();
          await loadAgents();
        }));
      }
      bindDocActions();

      const drop = $('#eDrop', host);
      const input = $('#eFiles', host);
      drop.addEventListener('click', () => input.click());
      drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
      drop.addEventListener('dragleave', () => drop.classList.remove('over'));
      drop.addEventListener('drop', async (e) => {
        e.preventDefault();
        drop.classList.remove('over');
        await uploadFiles(agentId, Array.from(e.dataTransfer.files));
        await pollDocs();
        await loadAgents();
        await loadHealth();
      });
      input.addEventListener('change', async () => {
        await uploadFiles(agentId, Array.from(input.files));
        input.value = '';
        await pollDocs();
        await loadAgents();
        await loadHealth();
      });

      $('[data-save]', host).addEventListener('click', async () => {
        const payload = {
          name: $('#eName', host).value.trim(),
          purpose: $('#ePurpose', host).value,
          observations: $('#eObs', host).value,
          prompt_override: $('#eOverride', host).value,
          use_master: $('#eUseMaster', host).checked,
          model: $('#eModel', host).value,
          temperature: Number($('#eTemp', host).value),
          top_k: Number($('#eTopK', host).value),
        };
        if (!payload.name) { toast('Informe o nome do agente', '', 'error'); return; }
        try {
          await api(`/api/agents/${agentId}`, { method: 'PUT', body: payload });
          toast('Agente atualizado', '', 'success');
          close();
          await loadAgents();
        } catch (err) {
          toast('Nao foi possivel salvar', err.message, 'error');
        }
      });
    },
  });
}

async function uploadFiles(agentId, files) {
  if (!files.length) return null;
  const form = new FormData();
  files.forEach((f) => form.append('files', f));
  try {
    const result = await api(`/api/agents/${agentId}/documents`, { method: 'POST', body: form });
    if (result.rejected.length) {
      result.rejected.forEach((r) => toast(`Arquivo recusado: ${r.filename}`, r.reason, 'error'));
    }
    if (result.created.length) {
      toast(`${result.created.length} arquivo(s) em processamento`, 'Extraindo texto e gerando embeddings.', 'success');
    }
    return result;
  } catch (err) {
    toast('Falha no upload', err.message, 'error');
    return null;
  }
}

/* ------------------------------------------------------------------- chat */
async function loadConversations() {
  if (!state.chatAgentId) { renderConversations([]); return; }
  const data = await api(`/api/agents/${state.chatAgentId}/conversations`);
  renderConversations(data.conversations);
}

function renderConversations(list) {
  const host = $('#convList');
  if (!list.length) {
    host.innerHTML = '<p class="small subtle" style="padding:6px 10px">Nenhuma conversa ainda.</p>';
    return;
  }
  host.innerHTML = list.map((c) => `
    <button class="conv-item ${c.id === state.conversationId ? 'active' : ''}" data-conv="${c.id}">
      <span class="t">${escapeHtml(c.title)}</span>
      <span class="m">${c.messages} mensagens &middot; ha ${timeAgo(c.updated_at)}</span>
      <span class="del" data-delconv="${c.id}" title="Excluir">${icon('x')}</span>
    </button>`).join('');

  $$('[data-conv]', host).forEach((b) => b.addEventListener('click', (e) => {
    if (e.target.closest('[data-delconv]')) return;
    openConversation(b.dataset.conv);
  }));
  $$('[data-delconv]', host).forEach((b) => b.addEventListener('click', async (e) => {
    e.stopPropagation();
    await api(`/api/conversations/${b.dataset.delconv}`, { method: 'DELETE' });
    if (state.conversationId === b.dataset.delconv) { state.conversationId = null; renderChatMessages([]); }
    await loadConversations();
  }));
}

async function openConversation(conversationId) {
  state.conversationId = conversationId;
  const data = await api(`/api/conversations/${conversationId}/messages`);
  renderChatMessages(data.messages);
  await loadConversations();
}

function messageHtml(role, contentHtml, sources = []) {
  const isUser = role === 'user';
  const chips = sources.length
    ? `<div class="sources">${sources.map((s) => `
        <span class="source-chip" data-src='${escapeHtml(JSON.stringify(s))}'>
          <span class="n">${s.n}</span> ${escapeHtml(s.filename)}${s.location ? ` &middot; ${escapeHtml(s.location)}` : ''}
        </span>`).join('')}</div>`
    : '';
  return `
    <div class="msg ${isUser ? 'user' : 'assistant'}">
      <div class="avatar">${isUser ? 'EU' : icon('bot')}</div>
      <div class="body">
        <div class="who">${isUser ? 'Voce' : escapeHtml(currentAgentName())}</div>
        <div class="bubble">${contentHtml}</div>
        ${chips}
      </div>
    </div>`;
}

function currentAgentName() {
  const agent = state.agents.find((a) => a.id === state.chatAgentId);
  return agent ? agent.name : 'Agente';
}

function renderChatMessages(messages) {
  const host = $('#chatMessages');
  if (!messages.length) {
    const agent = state.agents.find((a) => a.id === state.chatAgentId);
    host.innerHTML = `
      <div class="empty">
        <div class="icon">${icon('chat')}</div>
        <h3>${agent ? escapeHtml(agent.name) : 'Nenhum agente ativo'}</h3>
        <p>${agent
          ? escapeHtml(agent.purpose || 'Faca uma pergunta para comecar.')
          : 'Crie um agente na aba "Criar agente" para comecar a conversar.'}</p>
      </div>`;
    return;
  }
  host.innerHTML = messages
    .map((m) => messageHtml(m.role, renderMarkdown(m.content), m.role === 'assistant' ? (m.sources || []) : []))
    .join('');
  bindSourceChips();
  scrollChatToBottom();
}

function bindSourceChips() {
  $$('.source-chip:not([data-bound])').forEach((chip) => {
    chip.dataset.bound = '1';
    chip.addEventListener('click', () => {
    let src;
    try { src = JSON.parse(chip.dataset.src); } catch (_) { return; }
    openModal({
      title: `${src.filename}${src.location ? ` - ${src.location}` : ''}`,
      wide: true,
      body: `<p class="small subtle">Relevancia ${(src.score * 100).toFixed(0)}%</p>
             <div class="preview-box">${escapeHtml(src.excerpt || '')}</div>`,
      footer: `<a class="btn btn-secondary" href="/api/documents/${src.document_id}/file" target="_blank">${icon('file')} Abrir arquivo</a>
               <button class="btn btn-ghost" data-close>Fechar</button>`,
      });
    });
  });
}

function scrollChatToBottom() {
  const scroll = $('#chatScroll');
  scroll.scrollTop = scroll.scrollHeight;
}

async function sendMessage() {
  const input = $('#composerInput');
  const text = input.value.trim();
  if (!text || state.streaming) return;
  if (!state.chatAgentId) { toast('Escolha um agente', 'Crie ou ative um agente antes de conversar.', 'error'); return; }

  input.value = '';
  input.style.height = 'auto';
  state.streaming = true;
  $('#btnSend').disabled = true;
  $('#composerStatus').textContent = 'consultando a base...';

  const host = $('#chatMessages');
  if ($('.empty', host)) host.innerHTML = '';
  host.insertAdjacentHTML('beforeend', messageHtml('user', renderMarkdown(text)));
  host.insertAdjacentHTML('beforeend', messageHtml('assistant', '<span class="cursor">&#9613;</span>'));
  const bubble = host.lastElementChild.querySelector('.bubble');
  const bodyEl = host.lastElementChild.querySelector('.body');

  // indicador animado ao lado do nome do agente enquanto ele trabalha
  const whoEl = host.lastElementChild.querySelector('.who');
  whoEl.insertAdjacentHTML('beforeend', thinkingHtml('consultando a base'));
  const setThinking = (label) => {
    const el = whoEl.querySelector('.thinking .label');
    if (el) el.textContent = label;
  };
  const clearThinking = () => {
    const el = whoEl.querySelector('.thinking');
    if (el) el.remove();
  };

  scrollChatToBottom();

  let answer = '';
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        agent_id: state.chatAgentId,
        conversation_id: state.conversationId,
        message: text,
      }),
    });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop();

      for (const part of parts) {
        const evMatch = part.match(/^event: (.+)$/m);
        const dataMatch = part.match(/^data: (.*)$/m);
        if (!evMatch || !dataMatch) continue;
        let payload;
        try { payload = JSON.parse(dataMatch[1]); } catch (_) { continue; }

        if (evMatch[1] === 'meta') {
          state.conversationId = payload.conversation_id;
          setThinking('pensando');
          $('#composerStatus').textContent = payload.sources.length
            ? `${payload.sources.length} trecho(s) recuperado(s) - gerando resposta`
            : 'sem trecho relevante na base - gerando resposta';
          if (payload.sources.length) {
            bodyEl.insertAdjacentHTML('beforeend', `<div class="sources">${payload.sources.map((s) => `
              <span class="source-chip" data-src='${escapeHtml(JSON.stringify(s))}'>
                <span class="n">${s.n}</span> ${escapeHtml(s.filename)}${s.location ? ` &middot; ${escapeHtml(s.location)}` : ''}
              </span>`).join('')}</div>`);
            bindSourceChips();
          }
        } else if (evMatch[1] === 'token') {
          if (!answer) setThinking('escrevendo');
          answer += payload.t;
          bubble.innerHTML = `${renderMarkdown(answer)}<span class="cursor">&#9613;</span>`;
          scrollChatToBottom();
        } else if (evMatch[1] === 'error') {
          throw new Error(payload.message);
        }
      }
    }
    bubble.innerHTML = renderMarkdown(answer) || '<p class="muted">(resposta vazia)</p>';
  } catch (err) {
    bubble.innerHTML = `${renderMarkdown(answer)}<p class="small" style="color:#ff8a90">Erro: ${escapeHtml(err.message)}</p>`;
    toast('Falha na resposta', err.message, 'error');
  } finally {
    clearThinking();
    state.streaming = false;
    $('#btnSend').disabled = false;
    $('#composerStatus').textContent = '';
    await loadConversations();
    scrollChatToBottom();
  }
}

/* ------------------------------------------------------------ criar agente */
function renderPendingFiles() {
  const host = $('#cFileList');
  host.innerHTML = state.pendingFiles.map((f, i) => `
    <div class="file-row">
      <div class="ficon">${escapeHtml((f.name.split('.').pop() || '?').slice(0, 4))}</div>
      <div class="meta">
        <div class="name">${escapeHtml(f.name)}</div>
        <div class="desc">${formatBytes(f.size)}</div>
      </div>
      <button class="btn btn-ghost btn-icon btn-sm" data-rm="${i}">${icon('x')}</button>
    </div>`).join('');
  $$('[data-rm]', host).forEach((b) => b.addEventListener('click', () => {
    state.pendingFiles.splice(Number(b.dataset.rm), 1);
    renderPendingFiles();
  }));
}

function resetCreateForm() {
  ['cName', 'cPurpose', 'cObs', 'cOverride'].forEach((id) => { $(`#${id}`).value = ''; });
  $('#cTemp').value = '0.3';
  $('#cTopK').value = '5';
  $('#cUseMaster').checked = true;
  fillModelSelect($('#cModel'));
  state.pendingFiles = [];
  renderPendingFiles();
}

async function createAgent() {
  const name = $('#cName').value.trim();
  if (!name) { toast('Informe o nome do agente', '', 'error'); return; }

  const btn = $('#btnCreateAgent');
  btn.disabled = true;
  try {
    const agent = await api('/api/agents', {
      method: 'POST',
      body: {
        name,
        purpose: $('#cPurpose').value,
        observations: $('#cObs').value,
        prompt_override: $('#cOverride').value,
        use_master: $('#cUseMaster').checked,
        model: $('#cModel').value,
        temperature: Number($('#cTemp').value),
        top_k: Number($('#cTopK').value),
      },
    });
    toast('Agente criado', name, 'success');

    if (state.pendingFiles.length) {
      await uploadFiles(agent.id, state.pendingFiles);
      for (let i = 0; i < 60; i += 1) {
        const docs = await api(`/api/agents/${agent.id}/documents`);
        if (!docs.documents.some((d) => d.status === 'processing')) {
          const failed = docs.documents.filter((d) => d.status === 'error');
          if (failed.length) toast(`${failed.length} documento(s) com erro`, 'Veja os detalhes em Gerir agentes.', 'error');
          break;
        }
        await new Promise((r) => setTimeout(r, 1200));
      }
    }

    resetCreateForm();
    await loadAgents();
    await loadHealth();
    state.chatAgentId = agent.id;
    state.conversationId = null;
    renderAgentSelect();
    go('chat');
    renderChatMessages([]);
  } catch (err) {
    toast('Nao foi possivel criar o agente', err.message, 'error');
  } finally {
    btn.disabled = false;
  }
}

/* ----------------------------------------------------------- prompt mestre */
async function loadMasterPrompt() {
  const data = await api('/api/master-prompt');
  $('#masterPrompt').value = data.prompt;
  state.masterDirty = false;
  $('#masterState').textContent = 'salvo';
  $('#masterState').className = 'badge badge-primary';
}

function renderPreviewAgents() {
  const select = $('#previewAgent');
  if (!select) return;
  const agents = activeAgents();
  select.innerHTML = agents.length
    ? agents.map((a) => `<option value="${a.id}">${escapeHtml(a.name)}</option>`).join('')
    : '<option value="">Agente de exemplo</option>';
}

async function previewMaster() {
  const card = $('#masterPreviewCard');
  const data = await api('/api/master-prompt/preview', {
    method: 'POST',
    body: { prompt: $('#masterPrompt').value, agent_id: $('#previewAgent').value || null },
  });
  $('#masterPreviewText').textContent = data.preview;
  card.classList.remove('hidden');
  card.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/* ------------------------------------------------------- primeira execucao */
function copyText(text) {
  const done = () => toast('Copiado', text, 'success');
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
  } else {
    fallbackCopy(text, done);
  }
}

function fallbackCopy(text, done) {
  const area = document.createElement('textarea');
  area.value = text;
  area.style.position = 'fixed';
  area.style.opacity = '0';
  document.body.appendChild(area);
  area.select();
  try { document.execCommand('copy'); done(); } catch (_) { toast('Nao foi possivel copiar', text, 'error'); }
  area.remove();
}

async function loadSetup({ showIfMissing = false } = {}) {
  let data;
  try {
    data = await api('/api/setup');
  } catch (_) {
    return null;
  }
  state.setup = data;

  $('#requiredModel').textContent = data.required_model;
  $('#pullCommand').textContent = data.pull_command;
  $('[data-copy="ollama pull qwen2.5:3b"]').dataset.copy = data.pull_command;
  $('#ollamaUrlText').textContent = data.links.ollama_download;
  $('[data-copy="https://ollama.com/download"]').dataset.copy = data.links.ollama_download;
  $('#linkModelPage').textContent = data.links.ollama_model.replace('https://', '');

  const badgeOllama = $('#badgeOllama');
  badgeOllama.className = `badge ${data.ollama_online ? 'badge-success' : 'badge-danger'}`;
  badgeOllama.textContent = data.ollama_online ? 'rodando' : 'nao detectado';
  $('#stepOllama').classList.toggle('done', data.ollama_online);

  const badgeModel = $('#badgeModel');
  if (!data.ollama_online) {
    badgeModel.className = 'badge';
    badgeModel.textContent = 'aguardando o Ollama';
  } else if (data.has_required_model) {
    badgeModel.className = 'badge badge-success';
    badgeModel.textContent = 'instalado';
  } else {
    badgeModel.className = 'badge badge-warning';
    badgeModel.textContent = 'faltando';
  }
  $('#stepModel').classList.toggle('done', data.has_required_model);
  $('#btnPullModel').disabled = !data.ollama_online || data.has_required_model;
  $('#btnFinishSetup').disabled = !data.ready;

  if (showIfMissing && !data.ready) $('#setupOverlay').classList.remove('hidden');
  if (data.ready && state.pulling === false) {
    // nada a fazer; o usuario fecha quando quiser
  }
  return data;
}

async function pullModel() {
  if (state.pulling) return;
  state.pulling = true;
  const btn = $('#btnPullModel');
  btn.disabled = true;
  $('#pullProgress').classList.remove('hidden');
  $('#pullStatus').textContent = 'conectando ao Ollama...';
  $('#pullPercent').textContent = '';
  $('#pullBar').style.width = '0%';

  try {
    const res = await fetch('/api/models/pull', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: state.setup ? state.setup.required_model : null }),
    });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop();
      for (const part of parts) {
        const ev = part.match(/^event: (.+)$/m);
        const dt = part.match(/^data: (.*)$/m);
        if (!ev || !dt) continue;
        let payload;
        try { payload = JSON.parse(dt[1]); } catch (_) { continue; }

        if (ev[1] === 'progress') {
          $('#pullStatus').textContent = payload.status || 'baixando...';
          if (payload.percent != null) {
            $('#pullBar').style.width = `${payload.percent}%`;
            $('#pullPercent').textContent = `${payload.percent}% de ${formatBytes(payload.total)}`;
          }
        } else if (ev[1] === 'error') {
          throw new Error(payload.message);
        } else if (ev[1] === 'done') {
          $('#pullBar').style.width = '100%';
          $('#pullStatus').textContent = 'modelo instalado';
          $('#pullPercent').textContent = '100%';
        }
      }
    }
    toast('Modelo instalado', 'O NEXOS ja pode conversar.', 'success');
  } catch (err) {
    $('#pullStatus').textContent = `erro: ${err.message}`;
    toast('Falha ao baixar o modelo', err.message, 'error');
    btn.disabled = false;
  } finally {
    state.pulling = false;
    await loadSetup();
    await loadHealth();
  }
}

function bindSetupEvents() {
  $('#btnOpenOllama').addEventListener('click', async () => {
    try {
      await api('/api/open-link', { method: 'POST', body: { target: 'ollama_download' } });
      toast('Abrindo o site oficial do Ollama', 'ollama.com/download', 'success');
    } catch (err) {
      toast('Nao consegui abrir o navegador', 'Copie o link e abra manualmente.', 'error');
    }
  });
  $('#linkModelPage').addEventListener('click', async (e) => {
    e.preventDefault();
    await api('/api/open-link', { method: 'POST', body: { target: 'ollama_model' } }).catch(() => {});
  });
  $('#btnRecheck').addEventListener('click', async () => {
    const data = await loadSetup();
    await loadHealth();
    if (data && data.ready) toast('Tudo pronto', 'Ollama e modelo detectados.', 'success');
    else if (data && !data.ollama_online) toast('Ollama ainda nao respondeu', 'Confirme se ele esta aberto na bandeja.', 'warn');
  });
  $('#btnPullModel').addEventListener('click', pullModel);
  $('#btnSkipSetup').addEventListener('click', () => $('#setupOverlay').classList.add('hidden'));
  $('#btnFinishSetup').addEventListener('click', () => $('#setupOverlay').classList.add('hidden'));
  $$('[data-copy]').forEach((b) => b.addEventListener('click', () => copyText(b.dataset.copy)));
  $('.status-card').addEventListener('click', async () => {
    await loadSetup();
    $('#setupOverlay').classList.remove('hidden');
  });
}

/* ------------------------------------------------------------------ views */
const VIEW_META = {
  chat: { title: 'Chat', sub: 'Converse com um agente e sua base de conhecimento' },
  create: { title: 'Criar agente', sub: 'Defina identidade e envie os documentos' },
  manage: { title: 'Gerir agentes', sub: 'Editar, arquivar ou excluir agentes' },
  master: { title: 'Prompt mestre', sub: 'Politica global aplicada a todos os agentes' },
};

function go(view) {
  state.view = view;
  const current = (location.hash || '').replace(/^#/, '');
  if (current !== view && !current.startsWith(`${view}/`)) location.hash = view;
  $$('.view').forEach((v) => v.classList.add('hidden'));
  $(`#view-${view}`).classList.remove('hidden');
  $$('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.view === view));
  $('#viewTitle').textContent = VIEW_META[view].title;
  $('#viewSub').textContent = VIEW_META[view].sub;

  const actions = $('#headerActions');
  actions.innerHTML = view === 'manage'
    ? `<button class="btn btn-primary btn-sm" id="btnGoCreate">${icon('plus')} Novo agente</button>`
    : '';
  const goCreate = $('#btnGoCreate');
  if (goCreate) goCreate.addEventListener('click', () => go('create'));

  if (view === 'chat') scrollChatToBottom();
  if (view === 'master') { renderPreviewAgents(); loadMasterPrompt(); }
}

/* ------------------------------------------------------------------- init */
function bindEvents() {
  $$('.nav-item').forEach((b) => b.addEventListener('click', () => go(b.dataset.view)));
  $('#btnRefreshStatus').addEventListener('click', async () => {
    await api('/api/embeddings/refresh', { method: 'POST' });
    await loadHealth();
    toast('Status atualizado', '', 'success');
  });

  // chat
  $('#chatAgent').addEventListener('change', async (e) => {
    state.chatAgentId = e.target.value;
    state.conversationId = null;
    updateChatBadge();
    renderChatMessages([]);
    await loadConversations();
  });
  const newConv = async () => {
    state.conversationId = null;
    renderChatMessages([]);
    await loadConversations();
    $('#composerInput').focus();
  };
  $('#btnNewConv').addEventListener('click', newConv);
  $('#btnNewConv2').addEventListener('click', newConv);
  $('#btnSend').addEventListener('click', sendMessage);

  const composer = $('#composerInput');
  composer.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  composer.addEventListener('input', () => {
    composer.style.height = 'auto';
    composer.style.height = `${Math.min(composer.scrollHeight, 190)}px`;
  });

  // criar
  const drop = $('#cDrop');
  const input = $('#cFiles');
  drop.addEventListener('click', () => input.click());
  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', (e) => {
    e.preventDefault();
    drop.classList.remove('over');
    state.pendingFiles.push(...Array.from(e.dataTransfer.files));
    renderPendingFiles();
  });
  input.addEventListener('change', () => {
    state.pendingFiles.push(...Array.from(input.files));
    input.value = '';
    renderPendingFiles();
  });
  $('#btnCreateAgent').addEventListener('click', createAgent);
  $('#btnResetCreate').addEventListener('click', resetCreateForm);

  // gerir
  $$('#agentFilter button').forEach((b) => b.addEventListener('click', () => {
    state.filter = b.dataset.filter;
    $$('#agentFilter button').forEach((x) => x.classList.toggle('active', x === b));
    renderAgentGrid();
  }));
  $('#agentSearch').addEventListener('input', (e) => { state.search = e.target.value; renderAgentGrid(); });

  // mestre
  $('#masterPrompt').addEventListener('input', () => {
    state.masterDirty = true;
    $('#masterState').textContent = 'nao salvo';
    $('#masterState').className = 'badge badge-warning';
  });
  $('#btnMasterSave').addEventListener('click', async () => {
    try {
      await api('/api/master-prompt', { method: 'PUT', body: { prompt: $('#masterPrompt').value } });
      state.masterDirty = false;
      $('#masterState').textContent = 'salvo';
      $('#masterState').className = 'badge badge-primary';
      toast('Prompt mestre salvo', 'Vale para todos os agentes que usam o mestre.', 'success');
    } catch (err) {
      toast('Falha ao salvar', err.message, 'error');
    }
  });
  $('#btnMasterReset').addEventListener('click', () => {
    confirmModal('Restaurar padrao', 'O prompt mestre atual sera substituido pelo texto padrao do NEXOS.', 'Restaurar', async () => {
      const data = await api('/api/master-prompt/reset', { method: 'POST' });
      $('#masterPrompt').value = data.prompt;
      state.masterDirty = false;
      $('#masterState').textContent = 'salvo';
      $('#masterState').className = 'badge badge-primary';
      toast('Prompt mestre restaurado', '', 'success');
    }, false);
  });
  $('#btnMasterPreview').addEventListener('click', previewMaster);
  $('#previewAgent').addEventListener('change', previewMaster);
  $$('.var-chip').forEach((chip) => chip.addEventListener('click', () => {
    const area = $('#masterPrompt');
    const pos = area.selectionStart;
    area.value = area.value.slice(0, pos) + chip.dataset.var + area.value.slice(area.selectionEnd);
    area.focus();
    area.selectionStart = area.selectionEnd = pos + chip.dataset.var.length;
    state.masterDirty = true;
  }));
}

async function init() {
  bindEvents();
  bindSetupEvents();
  await loadHealth();
  fillModelSelect($('#cModel'));
  await loadAgents();

  // deep link: #chat, #create, #manage, #master ou #chat/<id da conversa>
  const [hashView, hashConv] = (location.hash || '').replace(/^#/, '').split('/');
  const view = VIEW_META[hashView] ? hashView : 'chat';

  if (hashConv) {
    try {
      const data = await api(`/api/conversations/${hashConv}/messages`);
      state.chatAgentId = data.conversation.agent_id;
      renderAgentSelect();
      state.conversationId = hashConv;
      renderChatMessages(data.messages);
    } catch (_) { renderChatMessages([]); }
  } else {
    renderChatMessages([]);
  }
  await loadConversations();

  go(view);
  await loadSetup({ showIfMissing: true });
  setInterval(loadHealth, 30000);
}

window.nexos = { go, state };
init();
