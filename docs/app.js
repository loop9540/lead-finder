// Lead Finder — Static Site
let leads = [];
let contacts = {};
let stats = {};
let currentPage = "dashboard";
let leadsPage = 1;
let contactsPage = 1;
const PER_PAGE = 50;
let leadSort = { col: "company_name", dir: "asc" };
let leadFilters = { platform: "", admin: "", source: "", q: "" };
let contactSearch = "";

// --- Data Loading ---
let contactsLoaded = false;

async function loadData() {
    try {
        // Load leads and stats first (small files)
        const [l, s] = await Promise.all([
            fetch("data/leads.json").then(r => r.json()),
            fetch("data/stats.json").then(r => r.json()),
        ]);
        leads = l;
        stats = s;
        render();

        // Load contacts in background (large file)
        fetch("data/contacts.json")
            .then(r => r.json())
            .then(c => { contacts = c; contactsLoaded = true; if (currentPage === "contacts" || currentPage.startsWith("lead:")) render(); })
            .catch(e => console.warn("Contacts load failed:", e));
    } catch (e) {
        document.getElementById("app").innerHTML = `<div class="loading">Error loading data: ${e.message}</div>`;
    }
}

// --- Helpers ---
function fmt(n) { return n != null ? n.toLocaleString() : "0"; }
function fmtM(n) { return n ? "$" + Math.round(n / 1e6).toLocaleString() + "M" : ""; }
function esc(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

function getUnique(arr, key) {
    const vals = new Set(arr.map(r => r[key]).filter(Boolean));
    return [...vals].sort();
}

function filteredLeads() {
    let f = leads;
    if (leadFilters.platform) f = f.filter(r => r.platform === leadFilters.platform);
    if (leadFilters.admin) f = f.filter(r => r.admin === leadFilters.admin);
    if (leadFilters.source) f = f.filter(r => r.source === leadFilters.source);
    if (leadFilters.q) {
        const q = leadFilters.q.toLowerCase();
        f = f.filter(r => r.company_name.toLowerCase().includes(q));
    }
    // Sort
    f.sort((a, b) => {
        let va = a[leadSort.col] ?? "";
        let vb = b[leadSort.col] ?? "";
        if (typeof va === "number" && typeof vb === "number") {
            return leadSort.dir === "asc" ? va - vb : vb - va;
        }
        va = String(va).toLowerCase();
        vb = String(vb).toLowerCase();
        return leadSort.dir === "asc" ? va.localeCompare(vb) : vb.localeCompare(va);
    });
    return f;
}

function filteredContacts() {
    // Flatten contacts into array with lead info
    const arr = [];
    for (const [lid, cs] of Object.entries(contacts)) {
        const lead = leads.find(l => l.id == lid);
        if (!lead) continue;
        for (const c of cs) {
            arr.push({ ...c, lead_id: lid, lead_company: lead.company_name, platform: lead.platform, admin: lead.admin });
        }
    }
    if (contactSearch) {
        const q = contactSearch.toLowerCase();
        return arr.filter(c =>
            (c.first_name + " " + c.last_name).toLowerCase().includes(q) ||
            (c.email || "").toLowerCase().includes(q) ||
            (c.lead_company || "").toLowerCase().includes(q)
        );
    }
    return arr;
}

// --- Rendering ---
function render() {
    if (currentPage === "dashboard") renderDashboard();
    else if (currentPage === "leads") renderLeads();
    else if (currentPage === "contacts") renderContacts();
    else if (currentPage.startsWith("lead:")) renderLeadDetail(currentPage.split(":")[1]);
}

function renderDashboard() {
    const platforms = {};
    const admins = {};
    leads.forEach(l => {
        if (l.platform) platforms[l.platform] = (platforms[l.platform] || 0) + 1;
        if (l.admin) admins[l.admin] = (admins[l.admin] || 0) + 1;
    });
    const sortedP = Object.entries(platforms).sort((a, b) => b[1] - a[1]);
    const sortedA = Object.entries(admins).sort((a, b) => b[1] - a[1]);

    document.getElementById("app").innerHTML = `
        <h1>Dashboard</h1>
        <div class="stats-cards">
            <div class="card big"><div class="card-number">${fmt(stats.total_leads)}</div><div class="card-label">Total Leads</div></div>
            <div class="card"><div class="card-number">${fmt(stats.total_contacts)}</div><div class="card-label">Contacts</div></div>
            <div class="card"><div class="card-number">${fmt(stats.contacts_with_email)}</div><div class="card-label">With Email</div></div>
            <div class="card"><div class="card-number">${fmt(stats.leads_matched)}</div><div class="card-label">Leads Matched</div></div>
        </div>
        <div class="grid-2">
            <div>
                <h2>By Tech Platform</h2>
                <table><thead><tr><th>Tech Platform</th><th>Leads</th></tr></thead><tbody>
                ${sortedP.map(([p, c]) => `<tr><td><a onclick="filterLeads('platform','${esc(p)}')">${esc(p)}</a></td><td>${fmt(c)}</td></tr>`).join("")}
                <tr style="font-weight:700;border-top:2px solid #e2e8f0"><td>Total</td><td>${fmt(sortedP.reduce((s, r) => s + r[1], 0))}</td></tr>
                </tbody></table>
            </div>
            <div>
                <h2>By Fund Administrator</h2>
                <table><thead><tr><th>Fund Admin</th><th>Leads</th></tr></thead><tbody>
                ${sortedA.map(([a, c]) => `<tr><td><a onclick="filterLeads('admin','${esc(a)}')">${esc(a)}</a></td><td>${fmt(c)}</td></tr>`).join("")}
                <tr style="font-weight:700;border-top:2px solid #e2e8f0"><td>Total</td><td>${fmt(sortedA.reduce((s, r) => s + r[1], 0))}</td></tr>
                </tbody></table>
            </div>
        </div>
    `;
}

function renderLeads() {
    const f = filteredLeads();
    const total = f.length;
    const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));
    leadsPage = Math.min(leadsPage, totalPages);
    const start = (leadsPage - 1) * PER_PAGE;
    const page = f.slice(start, start + PER_PAGE);

    const platforms = getUnique(leads, "platform");
    const adminsList = getUnique(leads, "admin");
    const sources = getUnique(leads, "source");

    function thClass(col) {
        if (leadSort.col === col) return `class="sorted-${leadSort.dir}"`;
        return "";
    }

    document.getElementById("app").innerHTML = `
        <h1>Leads <span class="count">(${fmt(total)})</span></h1>
        <div class="filters">
            <select onchange="leadFilters.platform=this.value;leadsPage=1;render()">
                <option value="">All Tech Platforms</option>
                ${platforms.map(p => `<option value="${esc(p)}" ${p === leadFilters.platform ? "selected" : ""}>${esc(p)}</option>`).join("")}
            </select>
            <select onchange="leadFilters.admin=this.value;leadsPage=1;render()">
                <option value="">All Fund Admins</option>
                ${adminsList.map(a => `<option value="${esc(a)}" ${a === leadFilters.admin ? "selected" : ""}>${esc(a)}</option>`).join("")}
            </select>
            <select onchange="leadFilters.source=this.value;leadsPage=1;render()">
                <option value="">All Sources</option>
                ${sources.map(s => `<option value="${esc(s)}" ${s === leadFilters.source ? "selected" : ""}>${esc(s)}</option>`).join("")}
            </select>
            <input type="text" placeholder="Search sponsor..." value="${esc(leadFilters.q)}"
                   oninput="leadFilters.q=this.value;leadsPage=1;render()">
            ${(leadFilters.platform || leadFilters.admin || leadFilters.source || leadFilters.q) ?
                '<a class="btn btn-secondary" onclick="clearLeadFilters()">Clear</a>' : ""}
        </div>
        <div class="table-actions">
            <button onclick="exportOutreach()">Export for Outreach.io</button>
            <button class="btn-secondary" onclick="exportCSV()">Export CSV</button>
        </div>
        <table>
            <thead><tr>
                <th ${thClass("company_name")} onclick="sortLeads('company_name')">Sponsor</th>
                <th ${thClass("aum")} onclick="sortLeads('aum')">AUM</th>
                <th ${thClass("fund_count")} onclick="sortLeads('fund_count')">Funds</th>
                <th ${thClass("platform")} onclick="sortLeads('platform')">Tech Platform</th>
                <th ${thClass("admin")} onclick="sortLeads('admin')">Fund Admin</th>
                <th>Source</th>
                <th ${thClass("contact_count")} onclick="sortLeads('contact_count')">Contacts</th>
            </tr></thead>
            <tbody>
            ${page.map(l => `<tr>
                <td><a onclick="showLead(${l.id})">${esc(l.company_name)}</a></td>
                <td>${l.aum ? fmtM(l.aum) : '<span class="empty-cell">-</span>'}</td>
                <td>${l.fund_count || '<span class="empty-cell">-</span>'}</td>
                <td>${l.platform || '<span class="empty-cell">-</span>'}</td>
                <td>${l.admin || '<span class="empty-cell">-</span>'}</td>
                <td>${esc(l.source)}</td>
                <td>${l.contact_count ? `<a onclick="showLead(${l.id})">${l.contact_count}</a>` : '<span class="empty-cell">-</span>'}</td>
            </tr>`).join("")}
            </tbody>
        </table>
        ${totalPages > 1 ? `<div class="pagination">
            ${leadsPage > 1 ? `<a onclick="leadsPage--;render()">Previous</a>` : ""}
            <span>Page ${leadsPage} of ${totalPages}</span>
            ${leadsPage < totalPages ? `<a onclick="leadsPage++;render()">Next</a>` : ""}
        </div>` : ""}
    `;
}

function renderContacts() {
    const f = filteredContacts();
    const total = f.length;
    const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));
    contactsPage = Math.min(contactsPage, totalPages);
    const start = (contactsPage - 1) * PER_PAGE;
    const page = f.slice(start, start + PER_PAGE);

    document.getElementById("app").innerHTML = `
        <h1>Contacts <span class="count">(${fmt(total)})</span></h1>
        <div class="filters">
            <input type="text" placeholder="Search name, email, or sponsor..." value="${esc(contactSearch)}"
                   oninput="contactSearch=this.value;contactsPage=1;render()">
            ${contactSearch ? '<a class="btn btn-secondary" onclick="clearContactSearch()">Clear</a>' : ""}
        </div>
        <table>
            <thead><tr>
                <th>Name</th><th>Title</th><th>Company</th><th>Platform</th><th>Email</th>
            </tr></thead>
            <tbody>
            ${page.map(c => `<tr>
                <td>${esc(c.first_name || "")} ${esc(c.last_name || "")}</td>
                <td>${esc(c.title || "")}</td>
                <td><a onclick="showLead(${c.lead_id})">${esc(c.lead_company || "")}</a></td>
                <td>${esc(c.platform || c.admin || "")}</td>
                <td>${c.email ? `<a href="mailto:${esc(c.email)}">${esc(c.email)}</a>` : ""}</td>
            </tr>`).join("")}
            </tbody>
        </table>
        ${totalPages > 1 ? `<div class="pagination">
            ${contactsPage > 1 ? `<a onclick="contactsPage--;render()">Previous</a>` : ""}
            <span>Page ${contactsPage} of ${totalPages}</span>
            ${contactsPage < totalPages ? `<a onclick="contactsPage++;render()">Next</a>` : ""}
        </div>` : ""}
    `;
}

function renderLeadDetail(id) {
    const lead = leads.find(l => l.id == id);
    if (!lead) { navigate("leads"); return; }
    const cs = contacts[String(id)] || [];

    document.getElementById("app").innerHTML = `
        <a class="back-link" onclick="navigate('leads')">&larr; Back to leads</a>
        <h1>${esc(lead.company_name)}</h1>
        <div class="detail-card">
            ${lead.aum ? `<p><strong>AUM:</strong> ${fmtM(lead.aum)}</p>` : ""}
            ${lead.total_gav ? `<p><strong>Total Fund GAV:</strong> ${fmtM(lead.total_gav)}</p>` : ""}
            ${lead.fund_count ? `<p><strong>Funds:</strong> ${lead.fund_count}</p>` : ""}
            ${lead.fund_types ? `<p><strong>Fund Types:</strong> ${esc(lead.fund_types)}</p>` : ""}
            ${lead.platform ? `<p><strong>Tech Platform:</strong> ${esc(lead.platform)}</p>` : ""}
            ${lead.admin ? `<p><strong>Fund Admin:</strong> ${esc(lead.admin)}</p>` : ""}
            ${lead.domain ? `<p><strong>Domain:</strong> <a href="${lead.domain.startsWith("http") ? lead.domain : "https://" + lead.domain}" target="_blank">${esc(lead.domain)}</a></p>` : ""}
            <p><strong>Source:</strong> ${esc(lead.source)}</p>
        </div>
        <h2>Contacts <span class="count">(${cs.length})</span></h2>
        ${cs.length ? `<table>
            <thead><tr><th>Name</th><th>Title</th><th>Email</th><th>Status</th><th>Phone</th><th>LinkedIn</th></tr></thead>
            <tbody>
            ${cs.map(c => `<tr>
                <td>${esc(c.first_name || "")} ${esc(c.last_name || "")}</td>
                <td>${esc(c.title || "")}</td>
                <td>${c.email ? `<a href="mailto:${esc(c.email)}">${esc(c.email)}</a>` : ""}</td>
                <td>${esc(c.email_status || "")}</td>
                <td>${esc(c.phone || "")}</td>
                <td>${c.linkedin ? `<a href="${esc(c.linkedin)}" target="_blank">Profile</a>` : ""}</td>
            </tr>`).join("")}
            </tbody>
        </table>` : '<p style="color:#a0aec0">No contacts with email found for this lead.</p>'}
    `;
}

// --- Actions ---
function navigate(page) {
    currentPage = page;
    document.querySelectorAll(".nav-links a").forEach(a => {
        a.classList.toggle("active", a.dataset.page === page);
    });
    render();
}

function showLead(id) { currentPage = "lead:" + id; render(); window.scrollTo(0, 0); }

function sortLeads(col) {
    if (leadSort.col === col) leadSort.dir = leadSort.dir === "asc" ? "desc" : "asc";
    else { leadSort.col = col; leadSort.dir = col === "aum" || col === "fund_count" || col === "contact_count" ? "desc" : "asc"; }
    render();
}

function clearLeadFilters() {
    leadFilters = { platform: "", admin: "", source: "", q: "" };
    leadsPage = 1;
    render();
}

function clearContactSearch() {
    contactSearch = "";
    contactsPage = 1;
    render();
}

function filterLeads(key, val) {
    leadFilters[key] = val;
    leadsPage = 1;
    navigate("leads");
}

function exportCSV() {
    const f = filteredLeads();
    const headers = ["Sponsor", "AUM", "Funds", "Fund Types", "Tech Platform", "Fund Admin", "Source", "Domain", "Contacts"];
    const rows = f.map(l => [
        l.company_name, l.aum || "", l.fund_count || "", l.fund_types || "",
        l.platform || "", l.admin || "", l.source, l.domain || "", l.contact_count || ""
    ]);
    let csv = headers.join(",") + "\n";
    for (const row of rows) {
        csv += row.map(v => `"${String(v).replace(/"/g, '""')}"`).join(",") + "\n";
    }
    const blob = new Blob([csv], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "leads_export.csv";
    a.click();
}

// Title priority for contact ranking
const TITLE_PRIORITY = [
    /\b(ceo|chief executive)\b/i,
    /\b(cfo|chief financial)\b/i,
    /\b(coo|chief operating)\b/i,
    /\b(cio|chief investment)\b/i,
    /\b(president)\b/i,
    /\b(managing partner|managing director|managing member)\b/i,
    /\b(partner)\b/i,
    /\b(founder|co-founder)\b/i,
    /\b(evp|svp|executive vice president|senior vice president)\b/i,
    /\b(vp|vice president)\b/i,
    /\b(director)\b/i,
    /\b(controller|treasurer)\b/i,
];

function rankContact(c) {
    const title = (c.title || "").toLowerCase();
    for (let i = 0; i < TITLE_PRIORITY.length; i++) {
        if (TITLE_PRIORITY[i].test(title)) return i;
    }
    return TITLE_PRIORITY.length;
}

function exportOutreach() {
    if (!contactsLoaded) {
        alert("Contacts are still loading. Please wait a moment and try again.");
        return;
    }

    const f = filteredLeads().filter(l => l.contact_count > 0);
    const MAX_CONTACTS = 3;

    const headers = [
        "Sponsor", "New Funds", "Total AUM $",
        "First Name 1", "Last Name 1", "Title 1", "Email 1", "Phone 1",
    ];

    const rows = [];
    for (const l of f) {
        const cs = (contacts[String(l.id)] || [])
            .filter(c => c.email)
            .sort((a, b) => rankContact(a) - rankContact(b))
            .slice(0, 1);

        if (cs.length === 0) continue;

        const c = cs[0];
        rows.push([
            l.company_name,
            l.fund_count || "",
            l.aum ? Math.round(l.aum) : "",
            c.first_name || "",
            c.last_name || "",
            c.title || "",
            c.email || "",
            c.phone || "",
        ]);
    }

    let csv = headers.join(",") + "\n";
    for (const row of rows) {
        csv += row.map(v => `"${String(v).replace(/"/g, '""')}"`).join(",") + "\n";
    }
    const blob = new Blob([csv], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "outreach_export.csv";
    a.click();
}

// --- Nav Events ---
document.querySelectorAll(".nav-links a").forEach(a => {
    a.addEventListener("click", e => {
        e.preventDefault();
        navigate(a.dataset.page);
    });
});

// --- Init ---
loadData();
