/* UtilityDesk front-end: talks to the Flask REST API. */

const $ = (sel) => document.querySelector(sel);
const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const num = (n) => Number(n || 0).toLocaleString("en-IN");
const badge = (v) => `<span class="badge b-${esc(v)}">${esc(String(v).replace("_", " "))}</span>`;
const fmtDate = (s) => (s ? new Date(s.length === 10 ? s + "T00:00:00" : s + "Z").toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "—");
const fmtDateTime = (s) => (s ? new Date(s + "Z").toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—");
const unitOf = (u) => (u === "electricity" ? "kWh" : "kL");

async function api(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.message || `Request failed (${res.status})`);
  return data;
}

function toast(msg, isError = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (isError ? " error" : "");
  t.hidden = false;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => (t.hidden = true), 3000);
}

function openModal(title, html) {
  $("#modal-title").textContent = title;
  $("#modal-body").innerHTML = html;
  $("#modal").hidden = false;
}
function closeModal() { $("#modal").hidden = true; }
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

function formData(form) {
  const data = {};
  new FormData(form).forEach((v, k) => { if (v !== "") data[k] = v; });
  return data;
}

function table(headers, rows, emptyMsg = "No records found") {
  if (!rows.length) return `<div class="empty">${emptyMsg}</div>`;
  const th = headers.map((h) => `<th class="${h.num ? "num" : ""}">${h.label ?? h}</th>`).join("");
  return `<table><thead><tr>${th}</tr></thead><tbody>${rows.join("")}</tbody></table>`;
}

function pager(el, data, onPage) {
  if (!data.total) { el.innerHTML = ""; return; }
  el.innerHTML = `<span>${data.total} record(s) · page ${data.page} of ${data.pages}</span>
    <div><button class="btn sm" ${data.page <= 1 ? "disabled" : ""} data-p="${data.page - 1}">‹ Prev</button>
    <button class="btn sm" ${data.page >= data.pages ? "disabled" : ""} data-p="${data.page + 1}">Next ›</button></div>`;
  el.querySelectorAll("button[data-p]").forEach((b) => (b.onclick = () => onPage(+b.dataset.p)));
}

function debounce(fn, ms = 300) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

/* ---------------- Navigation ---------------- */
const loaders = { dashboard: () => loadDashboard(), customers: () => loadCustomers(), bills: () => loadBills(), complaints: () => loadComplaints() };

function show(view) {
  if (!loaders[view]) view = "dashboard";
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + view));
  document.querySelectorAll(".sidebar nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  loaders[view]();
}
window.addEventListener("hashchange", () => show(location.hash.slice(1)));

/* ---------------- Dashboard ---------------- */
const charts = {};
function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

async function loadDashboard() {
  try {
    const d = await api("GET", "/api/dashboard/summary");
    const resolvedRate = d.complaints.total
      ? Math.round(((d.complaints.by_status.resolved + d.complaints.by_status.closed) / d.complaints.total) * 100)
      : 0;
    $("#kpis").innerHTML = [
      ["Customers", num(d.customers.total), `${d.customers.active} active`],
      ["Total billed", money(d.billing.total_billed), `${d.billing.paid + d.billing.unpaid + d.billing.overdue} bills`],
      ["Collected", money(d.billing.collected), `${d.billing.paid} paid bills`],
      ["Outstanding", money(d.billing.outstanding), `${d.billing.unpaid} unpaid · ${d.billing.overdue} overdue`],
      ["Open complaints", num(d.complaints.by_status.open + d.complaints.by_status.in_progress), `${d.complaints.total} total`],
      ["Resolution rate", resolvedRate + "%", d.complaints.avg_resolution_hours != null ? `avg ${d.complaints.avg_resolution_hours} h to resolve` : "no resolutions yet"],
    ].map(([l, v, s]) => `<div class="kpi"><div class="label">${l}</div><div class="value">${v}</div><div class="sub">${esc(s)}</div></div>`).join("");

    renderCharts(d);

    $("#dash-complaints").innerHTML = table(
      ["Ticket", "Customer", "Priority", "Status"],
      d.recent_complaints.map((c) => `<tr onclick="viewComplaint(${c.id})" style="cursor:pointer">
        <td>${esc(c.ticket_no)}<span class="sub-text">${esc(c.subject)}</span></td><td>${esc(c.customer_name)}</td>
        <td>${badge(c.priority)}</td><td>${badge(c.status)}</td></tr>`),
      "No complaints yet"
    );
    $("#dash-overdue").innerHTML = table(
      ["Bill", "Customer", "Due", { label: "Amount", num: true }],
      d.overdue_bills.map((b) => `<tr onclick="viewBill(${b.id})" style="cursor:pointer">
        <td>${esc(b.bill_no)}<span class="sub-text">${esc(b.utility_type)}</span></td><td>${esc(b.customer_name)}</td>
        <td>${fmtDate(b.due_date)}</td><td class="num">${money(b.total_amount)}</td></tr>`),
      "No overdue bills 🎉"
    );
  } catch (e) { toast(e.message, true); }
}

function renderCharts(d) {
  if (!window.Chart) return; // CDN unavailable: KPIs and tables still work
  const text = cssVar("--muted"), grid = cssVar("--border");
  Chart.defaults.color = text;
  Chart.defaults.borderColor = grid;
  const labels = d.monthly.map((m) => new Date(m.month + "-01T00:00:00").toLocaleDateString("en-IN", { month: "short", year: "2-digit" }));

  charts.monthly?.destroy();
  charts.monthly = new Chart($("#chart-monthly"), {
    data: {
      labels,
      datasets: [
        { type: "bar", label: "Electricity", data: d.monthly.map((m) => m.electricity), backgroundColor: "#3b82f6", stack: "billed", borderRadius: 4 },
        { type: "bar", label: "Water", data: d.monthly.map((m) => m.water), backgroundColor: "#06b6d4", stack: "billed", borderRadius: 4 },
        { type: "line", label: "Collected", data: d.monthly.map((m) => m.collected), borderColor: "#10b981", backgroundColor: "#10b981", tension: 0.3, pointRadius: 3 },
      ],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom" }, tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${money(c.raw)}` } } },
      scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, ticks: { callback: (v) => "₹" + num(v) } } },
    },
  });

  const s = d.complaints.by_status;
  charts.complaints?.destroy();
  charts.complaints = new Chart($("#chart-complaints"), {
    type: "doughnut",
    data: {
      labels: ["Open", "In progress", "Resolved", "Closed"],
      datasets: [{ data: [s.open, s.in_progress, s.resolved, s.closed], backgroundColor: ["#3b82f6", "#f59e0b", "#10b981", "#94a3b8"], borderWidth: 0 }],
    },
    options: { maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "bottom" } } },
  });
}

/* ---------------- Customers ---------------- */
let custPage = 1;
async function loadCustomers(page = custPage) {
  custPage = page;
  const params = new URLSearchParams({ page, per_page: 10, q: $("#cust-q").value, connection_type: $("#cust-type").value });
  try {
    const data = await api("GET", "/api/customers?" + params);
    $("#cust-table").innerHTML = table(
      ["Account", "Name", "Contact", "Connection", { label: "Outstanding", num: true }, "Open complaints", "Status", ""],
      data.items.map((c) => `<tr>
        <td>${esc(c.account_no)}</td>
        <td><strong>${esc(c.name)}</strong><span class="sub-text">${esc(c.address)}</span></td>
        <td>${esc(c.email)}<span class="sub-text">${esc(c.phone)}</span></td>
        <td>${badge(c.connection_type)}</td>
        <td class="num">${money(c.outstanding_amount)}</td>
        <td>${c.open_complaints}</td>
        <td>${c.is_active ? badge("paid").replace(">paid<", ">active<") : badge("closed").replace(">closed<", ">inactive<")}</td>
        <td><div class="actions">
          <button class="btn sm" onclick="viewCustomer(${c.id})">View</button>
          <button class="btn sm" onclick="openCustomerForm(${c.id})">Edit</button>
          <button class="btn sm danger" onclick="deleteCustomer(${c.id}, ${esc(JSON.stringify(c.name))})">Delete</button>
        </div></td></tr>`)
    );
    pager($("#cust-pager"), data, loadCustomers);
  } catch (e) { toast(e.message, true); }
}
$("#cust-q").addEventListener("input", debounce(() => loadCustomers(1)));
$("#cust-type").addEventListener("change", () => loadCustomers(1));

async function openCustomerForm(id) {
  const c = id ? await api("GET", `/api/customers/${id}`) : { connection_type: "residential", is_active: true };
  openModal(id ? `Edit ${c.account_no}` : "Add customer", `
    <form id="cust-form" class="form-grid">
      <div class="full"><label>Full name *</label><input name="name" required value="${esc(c.name)}"></div>
      <div><label>Email *</label><input name="email" type="email" required value="${esc(c.email)}"></div>
      <div><label>Phone *</label><input name="phone" required pattern="[0-9+\\- ]{7,20}" value="${esc(c.phone)}"></div>
      <div class="full"><label>Address *</label><input name="address" required value="${esc(c.address)}"></div>
      <div><label>Connection type</label><select name="connection_type">
        <option value="residential" ${c.connection_type === "residential" ? "selected" : ""}>Residential</option>
        <option value="commercial" ${c.connection_type === "commercial" ? "selected" : ""}>Commercial</option></select></div>
      ${id ? `<div><label>Account status</label><select name="is_active">
        <option value="1" ${c.is_active ? "selected" : ""}>Active</option><option value="" ${!c.is_active ? "selected" : ""}>Inactive</option></select></div>` : ""}
      <div class="form-actions full"><button type="button" class="btn" onclick="closeModal()">Cancel</button><button class="btn primary">${id ? "Save changes" : "Create customer"}</button></div>
    </form>`);
  $("#cust-form").onsubmit = async (e) => {
    e.preventDefault();
    const data = formData(e.target);
    if (id) data.is_active = e.target.is_active.value === "1";
    try {
      await api(id ? "PUT" : "POST", id ? `/api/customers/${id}` : "/api/customers", data);
      closeModal();
      toast(id ? "Customer updated" : "Customer created");
      loadCustomers();
    } catch (err) { toast(err.message, true); }
  };
}

async function viewCustomer(id) {
  try {
    const c = await api("GET", `/api/customers/${id}`);
    openModal(`${c.name} · ${c.account_no}`, `
      <div class="details">
        <div><span>Email</span>${esc(c.email)}</div><div><span>Phone</span>${esc(c.phone)}</div>
        <div><span>Connection</span>${badge(c.connection_type)}</div><div><span>Outstanding</span><strong>${money(c.outstanding_amount)}</strong></div>
        <div style="grid-column:1/-1"><span>Address</span>${esc(c.address)}</div>
      </div>
      <div class="section-title">Recent bills</div>
      ${table(["Bill", "Utility", "Units", { label: "Amount", num: true }, "Status"],
        c.recent_bills.map((b) => `<tr><td>${esc(b.bill_no)}</td><td>${badge(b.utility_type)}</td><td>${num(b.units_consumed)} ${unitOf(b.utility_type)}</td><td class="num">${money(b.total_amount)}</td><td>${badge(b.status)}</td></tr>`), "No bills")}
      <div class="section-title">Recent complaints</div>
      ${table(["Ticket", "Subject", "Status"],
        c.recent_complaints.map((x) => `<tr><td>${esc(x.ticket_no)}</td><td>${esc(x.subject)}</td><td>${badge(x.status)}</td></tr>`), "No complaints")}
      <div class="form-actions">
        <button class="btn" onclick="openBillForm(${c.id})">Generate bill</button>
        <button class="btn primary" onclick="openComplaintForm(${c.id})">Register complaint</button>
      </div>`);
  } catch (e) { toast(e.message, true); }
}

async function deleteCustomer(id, name) {
  if (!confirm(`Delete ${name}? All their bills and complaints will also be deleted.`)) return;
  try { await api("DELETE", `/api/customers/${id}`); toast("Customer deleted"); loadCustomers(); }
  catch (e) { toast(e.message, true); }
}

async function customerOptions(selectedId) {
  const data = await api("GET", "/api/customers?per_page=100&is_active=true");
  return data.items.map((c) => `<option value="${c.id}" ${c.id === selectedId ? "selected" : ""}>${esc(c.account_no)} — ${esc(c.name)} (${c.connection_type})</option>`).join("");
}

/* ---------------- Bills ---------------- */
let billPage = 1;
async function loadBills(page = billPage) {
  billPage = page;
  const params = new URLSearchParams({ page, per_page: 10, q: $("#bill-q").value, utility_type: $("#bill-utility").value, status: $("#bill-status").value });
  try {
    const data = await api("GET", "/api/bills?" + params);
    $("#bill-table").innerHTML = table(
      ["Bill no", "Customer", "Utility", "Period", { label: "Consumption", num: true }, { label: "Amount", num: true }, "Due", "Status", ""],
      data.items.map((b) => `<tr>
        <td>${esc(b.bill_no)}</td>
        <td>${esc(b.customer_name)}<span class="sub-text">${esc(b.account_no)}</span></td>
        <td>${badge(b.utility_type)}</td>
        <td>${fmtDate(b.period_start)} – ${fmtDate(b.period_end)}</td>
        <td class="num">${num(b.units_consumed)} ${unitOf(b.utility_type)}</td>
        <td class="num"><strong>${money(b.total_amount)}</strong>${b.late_fee ? `<span class="sub-text">incl. late fee ${money(b.late_fee)}</span>` : ""}</td>
        <td>${fmtDate(b.due_date)}</td>
        <td>${badge(b.status)}</td>
        <td><div class="actions">
          <button class="btn sm" onclick="viewBill(${b.id})">View</button>
          ${b.status !== "paid" ? `<button class="btn sm primary" onclick="payBill(${b.id})">Mark paid</button>` : ""}
          <button class="btn sm danger" onclick="deleteBill(${b.id}, ${esc(JSON.stringify(b.bill_no))})">Delete</button>
        </div></td></tr>`)
    );
    pager($("#bill-pager"), data, loadBills);
  } catch (e) { toast(e.message, true); }
}
$("#bill-q").addEventListener("input", debounce(() => loadBills(1)));
$("#bill-utility").addEventListener("change", () => loadBills(1));
$("#bill-status").addEventListener("change", () => loadBills(1));

function previewHtml(p, utility) {
  const slabs = p.breakdown.map((s) => `<div class="row"><span>${num(s.from)}–${s.to == null ? "∞" : num(s.to)} ${unitOf(utility)}: ${num(s.units)} × ₹${s.rate}</span><span>${money(s.amount)}</span></div>`).join("");
  return `<div class="row"><span>Units consumed</span><span>${num(p.units_consumed)} ${unitOf(utility)}</span></div>
    ${slabs}
    <div class="row"><span>Fixed charge</span><span>${money(p.fixed_charge)}</span></div>
    <div class="row"><span>Tax (5%)</span><span>${money(p.tax_amount)}</span></div>
    ${p.late_fee ? `<div class="row"><span>Late fee</span><span>${money(p.late_fee)}</span></div>` : ""}
    <div class="total"><span>Total</span><span>${money(p.total_amount)}</span></div>`;
}

async function openBillForm(customerId) {
  try {
    const opts = await customerOptions(customerId);
    openModal("Generate bill", `
      <form id="bill-form" class="form-grid">
        <div class="full"><label>Customer *</label><select name="customer_id" required><option value="">Select a customer…</option>${opts}</select></div>
        <div><label>Utility *</label><select name="utility_type"><option value="electricity">Electricity (kWh)</option><option value="water">Water (kL)</option></select></div>
        <div><label>Previous reading</label><input name="previous_reading" type="number" step="0.01" min="0" placeholder="Auto from last bill"></div>
        <div><label>Current reading *</label><input name="current_reading" type="number" step="0.01" min="0" required></div>
        <div><label>Period end</label><input name="period_end" type="date"></div>
        <div class="full preview" id="bill-preview">Enter readings to see the calculated bill.</div>
        <div class="form-actions full"><button type="button" class="btn" onclick="closeModal()">Cancel</button><button class="btn primary">Generate bill</button></div>
      </form>`);
    const form = $("#bill-form");
    const refresh = debounce(async () => {
      const data = formData(form);
      if (!data.customer_id || !data.current_reading) return;
      try { $("#bill-preview").innerHTML = previewHtml(await api("POST", "/api/bills/preview", data), data.utility_type); }
      catch (err) { $("#bill-preview").textContent = err.message; }
    });
    form.addEventListener("input", refresh);
    form.onsubmit = async (e) => {
      e.preventDefault();
      try {
        const bill = await api("POST", "/api/bills", formData(form));
        closeModal();
        toast(`Bill ${bill.bill_no} generated: ${money(bill.total_amount)}`);
        if (location.hash === "#bills") loadBills(1); else location.hash = "#bills";
      } catch (err) { toast(err.message, true); }
    };
  } catch (e) { toast(e.message, true); }
}

async function viewBill(id) {
  try {
    const b = await api("GET", `/api/bills/${id}`);
    openModal(`Bill ${b.bill_no}`, `
      <div class="details">
        <div><span>Customer</span>${esc(b.customer_name)}<span>${esc(b.account_no)}</span></div>
        <div><span>Utility</span>${badge(b.utility_type)}</div>
        <div><span>Status</span>${badge(b.status)}</div>
        <div><span>Billing period</span>${fmtDate(b.period_start)} – ${fmtDate(b.period_end)}</div>
        <div><span>Meter readings</span>${num(b.previous_reading)} → ${num(b.current_reading)}</div>
        <div><span>Issued / Due</span>${fmtDate(b.issue_date)} / ${fmtDate(b.due_date)}</div>
        ${b.paid_date ? `<div><span>Paid on</span>${fmtDate(b.paid_date)}</div>` : ""}
      </div>
      <div class="preview">${previewHtml(b, b.utility_type)}</div>
      <div class="form-actions">
        <button class="btn" onclick="closeModal()">Close</button>
        ${b.status !== "paid" ? `<button class="btn primary" onclick="payBill(${b.id})">Mark as paid</button>` : ""}
      </div>`);
  } catch (e) { toast(e.message, true); }
}

async function payBill(id) {
  try {
    const b = await api("POST", `/api/bills/${id}/pay`, {});
    closeModal();
    toast(`Payment recorded for ${b.bill_no}`);
    show(location.hash.slice(1) || "dashboard");
  } catch (e) { toast(e.message, true); }
}

async function deleteBill(id, no) {
  if (!confirm(`Delete bill ${no}?`)) return;
  try { await api("DELETE", `/api/bills/${id}`); toast("Bill deleted"); loadBills(); }
  catch (e) { toast(e.message, true); }
}

/* ---------------- Complaints ---------------- */
let compPage = 1;
async function loadComplaints(page = compPage) {
  compPage = page;
  const params = new URLSearchParams({
    page, per_page: 10, q: $("#comp-q").value, status: $("#comp-status").value,
    priority: $("#comp-priority").value, category: $("#comp-category").value,
  });
  try {
    const data = await api("GET", "/api/complaints?" + params);
    $("#comp-table").innerHTML = table(
      ["Ticket", "Customer", "Category", "Priority", "Status", "Assigned to", "Raised", ""],
      data.items.map((c) => `<tr>
        <td>${esc(c.ticket_no)}<span class="sub-text">${esc(c.subject)}</span></td>
        <td>${esc(c.customer_name)}<span class="sub-text">${esc(c.account_no)}</span></td>
        <td>${badge(c.category)}</td><td>${badge(c.priority)}</td><td>${badge(c.status)}</td>
        <td>${esc(c.assigned_to || "—")}</td><td>${fmtDateTime(c.created_at)}</td>
        <td><div class="actions">
          <button class="btn sm primary" onclick="viewComplaint(${c.id})">Manage</button>
          <button class="btn sm danger" onclick="deleteComplaint(${c.id}, ${esc(JSON.stringify(c.ticket_no))})">Delete</button>
        </div></td></tr>`)
    );
    pager($("#comp-pager"), data, loadComplaints);
  } catch (e) { toast(e.message, true); }
}
$("#comp-q").addEventListener("input", debounce(() => loadComplaints(1)));
["#comp-status", "#comp-priority", "#comp-category"].forEach((s) => $(s).addEventListener("change", () => loadComplaints(1)));

async function openComplaintForm(customerId) {
  try {
    const opts = await customerOptions(customerId);
    openModal("Register complaint", `
      <form id="comp-form" class="form-grid">
        <div class="full"><label>Customer *</label><select name="customer_id" required><option value="">Select a customer…</option>${opts}</select></div>
        <div><label>Category *</label><select name="category">
          <option value="electricity">Electricity supply</option><option value="water">Water supply</option>
          <option value="billing">Billing</option><option value="meter">Meter</option><option value="other">Other</option></select></div>
        <div><label>Priority</label><select name="priority">
          <option value="low">Low</option><option value="medium" selected>Medium</option><option value="high">High</option><option value="critical">Critical</option></select></div>
        <div class="full"><label>Subject *</label><input name="subject" required maxlength="150"></div>
        <div class="full"><label>Description *</label><textarea name="description" rows="4" required></textarea></div>
        <div class="form-actions full"><button type="button" class="btn" onclick="closeModal()">Cancel</button><button class="btn primary">Register</button></div>
      </form>`);
    $("#comp-form").onsubmit = async (e) => {
      e.preventDefault();
      try {
        const c = await api("POST", "/api/complaints", formData(e.target));
        closeModal();
        toast(`Complaint ${c.ticket_no} registered`);
        if (location.hash === "#complaints") loadComplaints(1); else location.hash = "#complaints";
      } catch (err) { toast(err.message, true); }
    };
  } catch (e) { toast(e.message, true); }
}

const NEXT_STATUSES = { open: ["open", "in_progress", "resolved", "closed"], in_progress: ["in_progress", "open", "resolved", "closed"], resolved: ["resolved", "in_progress", "closed"], closed: ["closed"] };

async function viewComplaint(id) {
  try {
    const c = await api("GET", `/api/complaints/${id}`);
    const statusOpts = NEXT_STATUSES[c.status].map((s) => `<option value="${s}" ${s === c.status ? "selected" : ""}>${s.replace("_", " ")}</option>`).join("");
    const prioOpts = ["low", "medium", "high", "critical"].map((p) => `<option ${p === c.priority ? "selected" : ""}>${p}</option>`).join("");
    openModal(`${c.ticket_no} · ${c.subject}`, `
      <div class="details">
        <div><span>Customer</span>${esc(c.customer_name)}<span>${esc(c.account_no)}</span></div>
        <div><span>Category</span>${badge(c.category)}</div>
        <div><span>Priority</span>${badge(c.priority)}</div>
        <div><span>Status</span>${badge(c.status)}</div>
        <div style="grid-column:1/-1"><span>Description</span>${esc(c.description)}</div>
      </div>
      <div class="section-title">History</div>
      <ul class="timeline">${c.history.map((h) => `<li><div>${badge(h.status)} ${esc(h.note || "")}</div><time>${fmtDateTime(h.created_at)} · ${esc(h.updated_by)}</time></li>`).join("")}</ul>
      ${c.status === "closed" ? `<p class="muted">This complaint is closed.</p>` : `
      <div class="section-title">Update complaint</div>
      <form id="comp-update" class="form-grid">
        <div><label>Status</label><select name="status">${statusOpts}</select></div>
        <div><label>Priority</label><select name="priority">${prioOpts}</select></div>
        <div><label>Assign to</label><input name="assigned_to" value="${esc(c.assigned_to)}" placeholder="Technician / department"></div>
        <div><label>Updated by</label><input name="updated_by" value="admin"></div>
        <div class="full"><label>Note</label><textarea name="note" rows="2" placeholder="Work done, findings, next steps…"></textarea></div>
        <div class="form-actions full"><button type="button" class="btn" onclick="closeModal()">Close</button><button class="btn primary">Save update</button></div>
      </form>`}`);
    const f = $("#comp-update");
    if (f) f.onsubmit = async (e) => {
      e.preventDefault();
      const data = formData(f);
      data.assigned_to = f.assigned_to.value; // allow clearing the assignee
      try {
        await api("PATCH", `/api/complaints/${id}`, data);
        toast("Complaint updated");
        viewComplaint(id);
        loaders[location.hash.slice(1) || "dashboard"]?.();
      } catch (err) { toast(err.message, true); }
    };
  } catch (e) { toast(e.message, true); }
}

async function deleteComplaint(id, no) {
  if (!confirm(`Delete complaint ${no}?`)) return;
  try { await api("DELETE", `/api/complaints/${id}`); toast("Complaint deleted"); loadComplaints(); }
  catch (e) { toast(e.message, true); }
}

show(location.hash.slice(1) || "dashboard");
