/* alexa+ vendo — client
   Voice/chat (left) + live data panel (right). Every panel is fetched by
   calling a tool on the MCP server; the spoken reply is grounded in that data. */

const $ = (s, r = document) => r.querySelector(s);
const chatScroll = $('#chatScroll');
const panelEmpty = $('#panelEmpty'), panelBody = $('#panelBody');

const INR = n => '₹' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const SUGGESTS = [
  "How's my cash looking today?",
  "What's running low in the kitchen?",
  "Show me supplier invoices",
  "Who's ordering near me?",
  "Any new reviews?",
];

/* ---------- boot ---------- */
(async function init() {
  renderSuggests();
  try {
    const bizId = localStorage.getItem('vendo_active_business_id');
    const url = bizId ? `/api/panel/business?business_id=${encodeURIComponent(bizId)}` : '/api/panel/business';
    const b = await fetch(url).then(r => r.json());
    $('#bizName').textContent = b.business_name || b.name || 'Your shop';
    $('#bizMeta').textContent = [b.locality, b.city, b.state].filter(Boolean).join(', ');
    const pill = $('#modePill');
    pill.textContent = '· online';
    pill.title = 'Alexa+ is connected to your business';
    // MCP proof chip: show how many tools the mounted MCP server exposes
    try {
      const t = await fetch('/api/mcp/tools').then(r => r.json());
      const chip = $('#mcpChip');
      if (chip && t.count) { chip.textContent = `MCP · ${t.count} tools`; chip.title = 'This frontend fetches every panel by calling the MCP server'; }
    } catch { /* non-fatal */ }
  } catch {
    $('#bizName').textContent = 'Backend offline';
    $('#bizMeta').textContent = 'start uvicorn to load data';
    $('#modePill').textContent = '· offline';
  }
  greet();
  // Deep-link a question: alexa.html#ask=How's my cash today?
  const ask = decodeURIComponent((location.hash.match(/#ask=(.*)$/) || [])[1] || '');
  if (ask) setTimeout(() => send(ask), 400);
})();

function greet() {
  addAlexa("Namaste! I'm keeping an eye on your shop. Ask me about your cash, stock, invoices, reviews, or the demand around you, and I'll show you the numbers as I answer.", null);
}

function renderSuggests() {
  const wrap = $('#suggests');
  SUGGESTS.forEach(s => {
    const c = document.createElement('button');
    c.className = 'chip'; c.type = 'button'; c.textContent = s;
    c.onclick = () => { if (!busy) send(s); };
    wrap.appendChild(c);
  });
}

/* ---------- chat ---------- */
let busy = false;

function bubble(cls, html) {
  const d = document.createElement('div');
  d.className = 'bubble ' + cls; d.innerHTML = html;
  chatScroll.appendChild(d);
  chatScroll.scrollTop = chatScroll.scrollHeight;
  return d;
}
function addUser(t) { bubble('user', esc(t)); }
function addAlexa(t, source) {
  const eq = '<span class="eq"><i style="height:50%"></i><i style="height:90%"></i><i style="height:35%"></i></span>';
  const src = source ? `<span class="src">↳ ${esc(source)}</span>` : '';
  bubble('alexa', `<div class="who">${eq} Alexa+</div><div>${esc(t)}</div>${src}`);
}
function addTyping() {
  return bubble('alexa', `<div class="who"><span class="eq"><i style="height:50%"></i><i style="height:90%"></i><i style="height:35%"></i></span> Alexa+</div><span class="typing"><i></i><i></i><i></i></span>`);
}

$('#composer').addEventListener('submit', e => {
  e.preventDefault();
  const v = $('#msg').value.trim();
  if (v && !busy) send(v);
});

async function send(text) {
  busy = true;
  $('#msg').value = '';
  addUser(text);
  pulseMic();
  const typing = addTyping();
  try {
    const bizId = localStorage.getItem('vendo_active_business_id');
    const res = await fetch('/api/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, business_id: bizId || undefined })
    }).then(r => r.json());
    typing.remove();
    const meta = { source: res.source, mcp: res.mcp || {} };
    addAlexa(res.reply, srcLabel(meta));
    const tool = lastTool(meta);
    const chip = $('#mcpChip');
    if (chip && tool) { chip.textContent = `MCP ▸ ${tool}()`; chip.classList.add('flash'); setTimeout(() => chip.classList.remove('flash'), 700); }
    if (res.panel && res.data) renderPanel(res.panel, res.data, meta);
  } catch {
    typing.remove();
    addAlexa("I couldn't reach the shop's data just now. Is the server running?", null);
  } finally { busy = false; }
}

/* mic is a simulated voice affordance (Alexa handles real STT in production) */
const mic = $('#mic');
mic.addEventListener('click', () => { mic.classList.toggle('listening'); $('#msg').focus(); });
function pulseMic() { mic.classList.add('listening'); setTimeout(() => mic.classList.remove('listening'), 1100); }

/* ---------- source labels (show which MCP tool served the data) ---------- */
const lastTool = meta => (meta && meta.mcp && meta.mcp.tools && meta.mcp.tools[meta.mcp.tools.length - 1]) || '';
function srcLabel(meta) {
  const tool = lastTool(meta);
  return tool ? `MCP · ${tool}()` : 'MCP';
}

/* ---------- visual panel ---------- */
function showPanel(label, title, hint, meta, cardsHTML) {
  panelEmpty.hidden = true; panelBody.hidden = false;
  $('#panelLabel').textContent = label;
  $('#panelTitle').textContent = title;
  $('#panelHint').textContent = hint || '';
  $('#panelSource').textContent = srcLabel(meta);
  $('#panelCards').innerHTML = cardsHTML;
  panelBody.scrollTop = 0;
}

const statusTag = s => s === 'critical' ? '<span class="tag crit">Critical</span>'
  : s === 'low' ? '<span class="tag low">Low</span>' : '<span class="tag ok">OK</span>';

function renderPanel(type, d, source) {
  const R = {
    accounts() {
      const pays = (d.upcoming || []).map(p =>
        `<tr><td>${esc(p.payee)}<div style="color:#6a3d52;font-size:.92rem">${esc(p.category)} · due ${esc(p.due_date)}</div></td>
         <td class="num">${INR(p.amount)}</td></tr>`).join('');
      showPanel('Accounts · Amazon Pay + Zoho', 'Cash position', 'Live balance against what you owe this week.', source, `
        <div class="dcard">
          <div class="stat-row">
            <div class="stat"><div class="k">Balance</div><div class="v amber">${INR(d.balance)}</div></div>
            <div class="stat"><div class="k">Safe to spend</div><div class="v ${d.usable <= 0 ? 'danger' : 'ok'}">${INR(d.usable)}</div><div class="sub">keeps ${INR(d.min_buffer)} buffer</div></div>
            <div class="stat"><div class="k">Due this week</div><div class="v danger">${INR(d.total_due)}</div></div>
          </div>
        </div>
        <div class="dcard"><h3>Upcoming payments</h3><div class="meta">${(d.upcoming || []).length} pending</div>
          <table class="dt"><thead><tr><th>Payee</th><th style="text-align:right">Amount</th></tr></thead><tbody>${pays}</tbody></table>
        </div>`);
    },
    inventory() {
      const rows = (d.items || []).map(it =>
        `<tr><td>${esc(it.name)}</td>
          <td class="num">${it.stock} ${esc(it.unit)}</td>
          <td class="num" style="color:#6a3d52">${it.reorder} ${esc(it.unit)}</td>
          <td style="text-align:right">${statusTag(it.status)}</td></tr>`).join('');
      showPanel('Inventory · from your DB', 'Kitchen stock', `${d.critical_count} out, ${d.low_count} below reorder point.`, source, `
        <div class="dcard">
          <div class="stat-row">
            <div class="stat"><div class="k">Needs ordering now</div><div class="v danger">${d.critical_count}</div></div>
            <div class="stat"><div class="k">Below reorder</div><div class="v amber">${d.low_count}</div></div>
            <div class="stat"><div class="k">Items tracked</div><div class="v">${(d.items || []).length}</div></div>
          </div>
        </div>
        <div class="dcard"><h3>Stock levels</h3>
          <table class="dt"><thead><tr><th>Item</th><th style="text-align:right">In stock</th><th style="text-align:right">Reorder at</th><th></th></tr></thead>
          <tbody>${rows}</tbody></table></div>`);
    },
    invoices() {
      const cards = (d.docs || []).map(doc => {
        const lines = (doc.lines || []).map(l =>
          `<tr><td>${esc(l.item)}</td><td class="num">${l.qty}</td><td class="num">${INR(l.unit_price)}</td><td class="num">${INR(l.total)}</td></tr>`).join('');
        return `<div class="dcard">
          <h3>${esc(doc.supplier)}</h3>
          <div class="meta mono">${esc(doc.invoice_number)} · ${esc(doc.date)} · ${Math.round((doc.confidence || 0) * 100)}% extracted</div>
          <table class="dt"><thead><tr><th>Item</th><th style="text-align:right">Qty</th><th style="text-align:right">Rate</th><th style="text-align:right">Total</th></tr></thead>
            <tbody>${lines}</tbody></table>
          <div class="stat-row" style="margin-top:12px">
            <div class="stat"><div class="k">Taxable</div><div class="v" style="font-size:1.5rem">${INR(doc.taxable)}</div></div>
            <div class="stat"><div class="k">GST</div><div class="v" style="font-size:1.5rem">${INR(doc.tax)}</div></div>
            <div class="stat"><div class="k">Total</div><div class="v amber" style="font-size:1.5rem">${INR(doc.total)}</div></div>
          </div></div>`;
      }).join('');
      showPanel('Invoices · Zoho Books', 'Supplier invoices', `${(d.docs || []).length} bills · ${INR(d.total)} total.`, source, cards);
    },
    market() {
      const segs = (d.segments || []).map(s => {
        const pct = Math.round((s.interest_score || 0) * 100);
        return `<div class="seg"><div class="nm">${esc(s.segment.replace(/_/g, ' '))}<div style="color:#6a3d52;font-size:.9rem">${s.est_households.toLocaleString('en-IN')} nearby · ${s.distance_km} km · ${INR(s.budget)}/meal</div></div>
          <div class="bar"><i style="width:${pct}%"></i></div><div class="vv">${pct}%</div></div>`;
      }).join('');
      showPanel('Market · Google Places', `Demand around ${esc(d.locality)}`, 'Who wants tiffin near you, by interest and reach.', source, `
        <div class="dcard"><h3>${esc(d.locality)}, ${esc(d.city)}</h3>
          <div class="meta">Customer segments within a few kilometres</div>${segs}</div>`);
    },
    reviews() {
      const items = (d.items || []).map(r =>
        `<div class="review"><div class="r-top"><b>${esc(r.author)}</b><span class="stars">${'★'.repeat(r.rating)}${'☆'.repeat(5 - r.rating)}</span><span>${esc(r.source)} · ${esc(r.date)}</span></div><p>${esc(r.text)}</p></div>`).join('');
      showPanel('Reviews · Google Business', 'What customers say', `${d.avg}★ average · ${d.positive_pct}% positive across ${d.count}.`, source, `
        <div class="dcard"><div class="stat-row">
          <div class="stat"><div class="k">Average</div><div class="v amber">${d.avg}★</div></div>
          <div class="stat"><div class="k">Positive</div><div class="v ok">${d.positive_pct}%</div></div>
          <div class="stat"><div class="k">Reviews</div><div class="v">${d.count}</div></div>
        </div></div>
        <div class="dcard"><h3>Recent</h3>${items}</div>`);
    },
    overview() {
      showPanel('Today · at a glance', 'Your shop right now', 'A quick read across cash, stock and demand.', source, `
        <div class="dcard"><div class="stat-row">
          <div class="stat"><div class="k">Cash balance</div><div class="v amber">${INR(d.balance)}</div></div>
          <div class="stat"><div class="k">Due this week</div><div class="v danger">${INR(d.total_due)}</div></div>
          <div class="stat"><div class="k">Low stock</div><div class="v ${d.low_count ? 'amber' : 'ok'}">${d.low_count}</div></div>
          <div class="stat"><div class="k">Reviews</div><div class="v">${d.avg}★</div></div>
        </div></div>`);
    },
  };
  (R[type] || R.overview)();
}
