import json
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
from database import db
import config

app = FastAPI(title="Autonomous Telegram Mirror Dashboard", docs_url=None, redoc_url=None)
security = HTTPBasic()


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Protects web dashboard with master password."""
    correct_password = secrets.compare_digest(credentials.password, config.DASHBOARD_PASSWORD)
    if not correct_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect admin password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# ------------------------------------------------------------------------------
# HEALTH CHECK (Render keep-alive & UptimeRobot)
# ------------------------------------------------------------------------------
@app.get("/health")
@app.get("/ping")
def health_check():
    return {
        "status": "online",
        "service": "telegram-mirror-engine",
        "database": db.db_type.upper(),
        "active_routes": len([m for m in db.get_mappings() if m.get("enabled", True)])
    }


# ------------------------------------------------------------------------------
# REST API (For dynamic controls, channels & settings)
# ------------------------------------------------------------------------------
@app.get("/api/user-channels", dependencies=[Depends(verify_credentials)])
async def api_get_user_channels(request: Request):
    """Fetches all joined channels & groups directly from Telegram via Telethon."""
    client = getattr(request.app.state, "telethon_client", None)
    if not client or not client.is_connected():
        return []
    try:
        dialogs = await client.get_dialogs()
        channels = []
        for d in dialogs:
            if d.is_channel:
                entity = d.entity
                username = getattr(entity, "username", None)
                is_admin = getattr(entity, "creator", False) or bool(getattr(entity, "admin_rights", None))
                channels.append({
                    "id": str(d.id),
                    "name": d.name,
                    "username": f"@{username}" if username else "No Username (Private)",
                    "is_admin": is_admin
                })
        return channels
    except Exception as e:
        print(f"[API Error] Failed fetching dialogs: {e}")
        return []


@app.get("/api/mappings", dependencies=[Depends(verify_credentials)])
def api_get_mappings():
    return db.get_mappings()


@app.post("/api/mappings", dependencies=[Depends(verify_credentials)])
async def api_save_mapping(request: Request):
    data = await request.json()
    new_id = db.save_mapping(data)
    return {"status": "success", "id": new_id}


@app.delete("/api/mappings/{mapping_id}", dependencies=[Depends(verify_credentials)])
def api_delete_mapping(mapping_id: str):
    deleted = db.delete_mapping(mapping_id)
    return {"status": "success" if deleted else "not_found"}


@app.post("/api/mappings/{mapping_id}/toggle", dependencies=[Depends(verify_credentials)])
def api_toggle_mapping(mapping_id: str):
    state = db.toggle_mapping(mapping_id)
    return {"status": "success", "new_state": state}


@app.get("/api/settings", dependencies=[Depends(verify_credentials)])
def api_get_settings():
    return db.get_telegram_config()


@app.post("/api/settings", dependencies=[Depends(verify_credentials)])
async def api_save_settings(request: Request):
    data = await request.json()
    db.save_telegram_config(data)
    return {"status": "success", "message": "Settings saved to MongoDB"}


@app.get("/api/history", dependencies=[Depends(verify_credentials)])
def api_get_history(limit: int = 50, offset: int = 0):
    return db.get_history(limit=limit, offset=offset)


@app.get("/api/stats", dependencies=[Depends(verify_credentials)])
def api_get_stats():
    return db.get_stats()


@app.get("/api/export", dependencies=[Depends(verify_credentials)])
def api_export_backup():
    data = {
        "settings": db.get_telegram_config(),
        "mappings": db.get_mappings(),
        "stats": db.get_stats(),
        "history": db.get_history(limit=500)
    }
    content = json.dumps(data, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=telegram_mirror_backup.json"}
    )


# ------------------------------------------------------------------------------
# FULLY ADVANCED GLASSMORPHISM WEB DASHBOARD
# ------------------------------------------------------------------------------
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Autonomous Telegram Mirror | Control Center</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #090d16;
            --card-bg: rgba(22, 28, 45, 0.7);
            --card-border: rgba(255, 255, 255, 0.08);
            --primary: #3b82f6;
            --primary-glow: rgba(59, 130, 246, 0.35);
            --success: #10b981;
            --danger: #ef4444;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
        body { background: var(--bg); color: var(--text-main); min-height: 100vh; padding: 24px; }
        .container { max-width: 1240px; margin: 0 auto; }
        
        /* Header */
        header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; flex-wrap: wrap; gap: 16px; }
        .logo { font-size: 22px; font-weight: 700; display: flex; align-items: center; gap: 10px; }
        .logo span { background: linear-gradient(135deg, #60a5fa, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .badge { background: rgba(16, 185, 129, 0.15); color: #34d399; padding: 4px 12px; border-radius: 20px; font-size: 13px; border: 1px solid rgba(52, 211, 153, 0.3); }

        /* Stats Cards */
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 30px; }
        .stat-card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 14px; padding: 18px; backdrop-filter: blur(12px); box-shadow: 0 8px 24px rgba(0,0,0,0.3); }
        .stat-card .label { font-size: 13px; color: var(--text-muted); font-weight: 500; }
        .stat-card .value { font-size: 28px; font-weight: 700; margin-top: 6px; color: #fff; }

        /* Navigation Tabs */
        .nav-tabs { display: flex; gap: 10px; margin-bottom: 24px; border-bottom: 1px solid var(--card-border); padding-bottom: 12px; flex-wrap: wrap; }
        .tab-btn { background: none; border: none; color: var(--text-muted); font-size: 14px; font-weight: 600; padding: 8px 16px; border-radius: 8px; cursor: pointer; transition: 0.2s; }
        .tab-btn.active { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(96, 165, 250, 0.3); }

        /* Tables & Content */
        .content-box { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 14px; padding: 22px; backdrop-filter: blur(12px); box-shadow: 0 10px 30px rgba(0,0,0,0.35); }
        .box-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 10px; }
        .btn { background: var(--primary); color: white; border: none; padding: 8px 18px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 8px; transition: 0.2s; }
        .btn:hover { box-shadow: 0 0 18px var(--primary-glow); }
        .btn-secondary { background: rgba(255,255,255,0.06); border: 1px solid var(--card-border); }

        table { width: 100%; border-collapse: collapse; margin-top: 10px; text-align: left; }
        th { color: var(--text-muted); font-size: 13px; text-transform: uppercase; padding: 12px 14px; border-bottom: 1px solid var(--card-border); }
        td { padding: 14px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); font-size: 14px; vertical-align: middle; }
        tr:hover { background: rgba(255,255,255,0.02); }

        /* Switches */
        .toggle-switch { position: relative; width: 44px; height: 24px; display: inline-block; }
        .toggle-switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background: #334155; border-radius: 24px; transition: 0.3s; }
        .slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px; background: white; border-radius: 50%; transition: 0.3s; }
        input:checked + .slider { background: var(--success); }
        input:checked + .slider:before { transform: translateX(20px); }

        /* Modal & Forms */
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); backdrop-filter: blur(8px); justify-content: center; align-items: center; z-index: 1000; overflow-y: auto; padding: 20px; }
        .modal-content { background: #131a29; border: 1px solid var(--card-border); border-radius: 16px; width: 620px; max-width: 95%; padding: 26px; max-height: 90vh; overflow-y: auto; }
        .form-group { margin-bottom: 16px; }
        .form-group label { display: block; font-size: 13px; color: var(--text-muted); margin-bottom: 6px; font-weight: 500; }
        .form-group input, .form-group textarea, .form-group select { width: 100%; padding: 10px 14px; background: #0c121e; border: 1px solid var(--card-border); border-radius: 8px; color: white; font-size: 14px; }
        .form-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 24px; }

        .advanced-accordion { background: rgba(255,255,255,0.02); border: 1px solid var(--card-border); border-radius: 10px; padding: 14px; margin-top: 14px; }
        .advanced-header { font-size: 13px; font-weight: 600; color: #60a5fa; cursor: pointer; display: flex; justify-content: space-between; }
        .advanced-body { display: none; margin-top: 14px; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo">
                🚀 <span>Autonomous Telegram Mirror Engine</span>
            </div>
            <div style="display:flex; gap:10px; align-items:center;">
                <span class="badge" id="db-badge">DB: LOADING</span>
                <a href="/api/export" class="btn btn-secondary" style="text-decoration:none;">📥 Export DB (JSON)</a>
            </div>
        </header>

        <!-- Stats Overview -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">Total Posts Forwarded</div>
                <div class="value" id="stat-posts">0</div>
            </div>
            <div class="stat-card">
                <div class="label">Links Converted</div>
                <div class="value" id="stat-links">0</div>
            </div>
            <div class="stat-card">
                <div class="label">Active Routes</div>
                <div class="value" id="stat-routes">0</div>
            </div>
            <div class="stat-card">
                <div class="label">System Errors</div>
                <div class="value" id="stat-errors" style="color:#f87171;">0</div>
            </div>
        </div>

        <!-- Tabs Navigation -->
        <div class="nav-tabs">
            <button class="tab-btn active" onclick="switchTab('mappings')">Channel Routes</button>
            <button class="tab-btn" onclick="switchTab('explorer')">🔍 Browse My Telegram Channels</button>
            <button class="tab-btn" onclick="switchTab('history')">Live Database History</button>
            <button class="tab-btn" onclick="switchTab('settings')">Telegram Account & Credentials</button>
        </div>

        <!-- TAB 1: Channel Mappings -->
        <div id="tab-mappings" class="content-box">
            <div class="box-header">
                <h3>Active Channel Routes</h3>
                <button class="btn" onclick="openAddModal()">+ Add New Route</button>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Status</th>
                        <th>Name</th>
                        <th>Source Channel</th>
                        <th>Target Channel</th>
                        <th>Converter Bot</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="mappings-body">
                    <tr><td colspan="6" style="text-align:center; color:#64748b;">Loading routes...</td></tr>
                </tbody>
            </table>
        </div>

        <!-- TAB 2: Browse My Telegram Channels -->
        <div id="tab-explorer" class="content-box" style="display:none;">
            <div class="box-header">
                <h3>My Joined Telegram Channels & Groups</h3>
                <button class="btn btn-secondary" onclick="loadUserChannels()">🔄 Refresh Channels</button>
            </div>
            <p style="color:#94a3b8; font-size:13px; margin-bottom:16px;">
                Here are all the channels your Telegram account is joined to. Click <strong>+ Create Route</strong> to instantly set any channel as your Source or Target!
            </p>
            <table>
                <thead>
                    <tr>
                        <th>Channel Name</th>
                        <th>Channel Numeric ID</th>
                        <th>Username / Privacy</th>
                        <th>Role</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody id="explorer-body">
                    <tr><td colspan="5" style="text-align:center; color:#64748b;">Scanning your Telegram account...</td></tr>
                </tbody>
            </table>
        </div>

        <!-- TAB 3: Live Database History -->
        <div id="tab-history" class="content-box" style="display:none;">
            <div class="box-header">
                <h3>Live Post & Link History (Stored in MongoDB)</h3>
                <button class="btn btn-secondary" onclick="loadHistory()">🔄 Refresh</button>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Time (UTC)</th>
                        <th>Source</th>
                        <th>Original Link</th>
                        <th>Converted Link</th>
                        <th>Target</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody id="history-body">
                    <tr><td colspan="6" style="text-align:center; color:#64748b;">Loading database logs...</td></tr>
                </tbody>
            </table>
        </div>

        <!-- TAB 4: Telegram Account & Settings -->
        <div id="tab-settings" class="content-box" style="display:none;">
            <div class="box-header">
                <h3>Telegram Credentials (Stored in MongoDB)</h3>
            </div>
            <p style="color:#94a3b8; font-size:13px; margin-bottom:20px;">
                These credentials are saved directly in your MongoDB Atlas database. When switching Render accounts, everything auto-loads seamlessly.
            </p>
            <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:16px;">
                <div class="form-group">
                    <label>Telegram API ID</label>
                    <input type="number" id="s_api_id">
                </div>
                <div class="form-group">
                    <label>Telegram API Hash</label>
                    <input type="text" id="s_api_hash">
                </div>
                <div class="form-group">
                    <label>Admin User ID (Harsh ID)</label>
                    <input type="number" id="s_admin_id">
                </div>
                <div class="form-group">
                    <label>Default Converter Bot</label>
                    <input type="text" id="s_conv_bot">
                </div>
                <div class="form-group">
                    <label>Bot Timeout (Seconds)</label>
                    <input type="number" id="s_timeout" value="25">
                </div>
                <div class="form-group">
                    <label>Album Buffer Window (Sec)</label>
                    <input type="number" step="0.5" id="s_buffer" value="2.0">
                </div>
            </div>
            <div class="form-group">
                <label>Telegram StringSession (Auth Token)</label>
                <textarea id="s_session" rows="4" style="font-family:monospace; font-size:12px;"></textarea>
            </div>
            <button class="btn" onclick="saveSettings()">💾 Save Credentials to MongoDB</button>
            <span id="settings-status" style="margin-left:12px; font-size:13px; color:#34d399;"></span>
        </div>
    </div>

    <!-- Datalist for Channel Auto-Suggestions -->
    <datalist id="channel-suggestions"></datalist>

    <!-- FULLY ADVANCED CUSTOM ROUTE MODAL -->
    <div id="addModal" class="modal">
        <div class="modal-content">
            <h3 style="margin-bottom:16px; font-size:18px;">Add New Custom Channel Route</h3>
            
            <div class="form-group">
                <label>Route Friendly Name</label>
                <input type="text" id="m_name" placeholder="e.g. VIP Leaks Mirror">
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:14px;">
                <div class="form-group">
                    <label>Source Channel (Pick or Paste ID)</label>
                    <input type="text" id="m_source" list="channel-suggestions" placeholder="Pick channel or paste ID">
                </div>
                <div class="form-group">
                    <label>Target Channel (Pick or Paste ID)</label>
                    <input type="text" id="m_target" list="channel-suggestions" placeholder="Pick channel or paste ID">
                </div>
            </div>

            <div class="form-group">
                <label>Converter Bot</label>
                <input type="text" id="m_bot" value="DW2DW_LinkConverterBot">
            </div>

            <div class="form-group">
                <label>Custom Header Banner (Optional)</label>
                <input type="text" id="m_header" placeholder="🔥 EXCLUSIVE UPDATE 🔥">
            </div>

            <div class="form-group">
                <label>Custom Footer Banner (Optional)</label>
                <input type="text" id="m_footer" placeholder="👉 Join @mychannel for more!">
            </div>

            <!-- Advanced Options Accordion -->
            <div class="advanced-accordion">
                <div class="advanced-header" onclick="toggleAdvanced()">
                    <span>⚙️ Advanced Custom Settings (Watermarks, Buttons, Delays)</span>
                    <span id="acc-arrow">▼</span>
                </div>
                <div id="advanced-fields" class="advanced-body">
                    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
                        <div class="form-group">
                            <label>Replace Watermark (@mention / link)</label>
                            <input type="text" id="m_wm_old" placeholder="e.g. @old_channel">
                        </div>
                        <div class="form-group">
                            <label>Replace With Your Handle</label>
                            <input type="text" id="m_wm_new" placeholder="e.g. @genz454">
                        </div>
                    </div>

                    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
                        <div class="form-group">
                            <label>Inline Button Text</label>
                            <input type="text" id="m_btn_text" placeholder="e.g. ⚡ Watch Online">
                        </div>
                        <div class="form-group">
                            <label>Post Delay (Seconds)</label>
                            <input type="number" id="m_delay" value="2" min="0" max="30">
                        </div>
                    </div>

                    <div style="margin-top:10px; display:flex; align-items:center; gap:10px;">
                        <input type="checkbox" id="m_strip" style="width:18px; height:18px;">
                        <label for="m_strip" style="margin:0; font-size:13px; color:#cbd5e1; cursor:pointer;">
                            Strip unconverted 3rd-party links from caption
                        </label>
                    </div>
                </div>
            </div>

            <div class="form-actions">
                <button class="btn btn-secondary" onclick="closeAddModal()">Cancel</button>
                <button class="btn" onclick="saveNewRoute()">Save Custom Route</button>
            </div>
        </div>
    </div>

    <script>
        let cachedChannels = [];

        function switchTab(tab) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('tab-mappings').style.display = 'none';
            document.getElementById('tab-explorer').style.display = 'none';
            document.getElementById('tab-history').style.display = 'none';
            document.getElementById('tab-settings').style.display = 'none';

            if (tab === 'mappings') {
                document.getElementById('tab-mappings').style.display = 'block';
                event.target.classList.add('active');
                loadMappings();
            } else if (tab === 'explorer') {
                document.getElementById('tab-explorer').style.display = 'block';
                event.target.classList.add('active');
                loadUserChannels();
            } else if (tab === 'history') {
                document.getElementById('tab-history').style.display = 'block';
                event.target.classList.add('active');
                loadHistory();
            } else if (tab === 'settings') {
                document.getElementById('tab-settings').style.display = 'block';
                event.target.classList.add('active');
                loadSettings();
            }
        }

        async function loadStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                document.getElementById('stat-posts').innerText = data.posts_forwarded || 0;
                document.getElementById('stat-links').innerText = data.links_converted || 0;
                document.getElementById('stat-routes').innerText = `${data.active_mappings} / ${data.total_mappings}`;
                document.getElementById('stat-errors').innerText = data.errors || 0;
                document.getElementById('db-badge').innerText = `DB: ${data.database_type}`;
            } catch (e) { console.error(e); }
        }

        async function loadMappings() {
            try {
                const res = await fetch('/api/mappings');
                const mappings = await res.json();
                const tbody = document.getElementById('mappings-body');
                if (!mappings.length) {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:#64748b;">No channel routes found. Click + Add New Route to create one.</td></tr>';
                    return;
                }
                tbody.innerHTML = mappings.map(m => `
                    <tr>
                        <td>
                            <label class="toggle-switch">
                                <input type="checkbox" ${m.enabled ? 'checked' : ''} onchange="toggleRoute('${m.id}')">
                                <span class="slider"></span>
                            </label>
                        </td>
                        <td><strong>${m.name}</strong></td>
                        <td><code>${m.source_channel}</code></td>
                        <td><code>${m.target_channel}</code></td>
                        <td><code>@${m.converter_bot}</code></td>
                        <td>
                            <button class="btn btn-secondary" style="color:#ef4444; padding:4px 10px; font-size:12px;" onclick="deleteRoute('${m.id}')">Delete</button>
                        </td>
                    </tr>
                `).join('');
            } catch (e) { console.error(e); }
        }

        async function loadUserChannels() {
            const tbody = document.getElementById('explorer-body');
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:#64748b;">Scanning your Telegram account...</td></tr>';
            try {
                const res = await fetch('/api/user-channels');
                cachedChannels = await res.json();
                
                // Populate Datalist
                const datalist = document.getElementById('channel-suggestions');
                datalist.innerHTML = cachedChannels.map(c => `
                    <option value="${c.id}">${c.name} (${c.username})</option>
                `).join('');

                if (!cachedChannels.length) {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:#64748b;">No channels found or Telegram is connecting. Try refreshing in 5 seconds.</td></tr>';
                    return;
                }

                tbody.innerHTML = cachedChannels.map(c => `
                    <tr>
                        <td><strong>${c.name}</strong></td>
                        <td><code>${c.id}</code></td>
                        <td><span style="color:${c.username.startsWith('@') ? '#60a5fa' : '#94a3b8'};">${c.username}</span></td>
                        <td>
                            <span class="badge" style="${c.is_admin ? 'background:rgba(59,130,246,0.15); color:#60a5fa;' : 'background:rgba(255,255,255,0.05); color:#94a3b8;'}">
                                ${c.is_admin ? 'Admin / Creator' : 'Member'}
                            </span>
                        </td>
                        <td>
                            <button class="btn btn-secondary" style="font-size:12px; padding:4px 10px;" onclick="quickCreateRoute('${c.id}', '${c.name.replace(/'/g, "\\'")}')">
                                + Set as Source
                            </button>
                        </td>
                    </tr>
                `).join('');
            } catch (e) {
                console.error(e);
                tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:#ef4444;">Error loading channels. Please ensure bot is connected.</td></tr>';
            }
        }

        function quickCreateRoute(channelId, channelName) {
            openAddModal();
            document.getElementById('m_name').value = `${channelName} to Target`;
            document.getElementById('m_source').value = channelId;
        }

        async function loadHistory() {
            try {
                const res = await fetch('/api/history?limit=30');
                const history = await res.json();
                const tbody = document.getElementById('history-body');
                if (!history.length) {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:#64748b;">No post logs in database yet.</td></tr>';
                    return;
                }
                tbody.innerHTML = history.map(h => `
                    <tr>
                        <td style="color:#94a3b8; font-size:12px;">${h.timestamp}</td>
                        <td><code>${h.source_channel}</code></td>
                        <td><a href="${h.original_url || '#'}" target="_blank" style="color:#60a5fa; text-decoration:none;">${(h.original_url || 'None').substring(0, 32)}...</a></td>
                        <td><a href="${h.converted_url || '#'}" target="_blank" style="color:#34d399; text-decoration:none;">${(h.converted_url || 'None').substring(0, 32)}...</a></td>
                        <td><code>${h.target_channel}</code></td>
                        <td>
                            <span class="badge" style="${h.status === 'success' ? '' : 'background:rgba(239,68,68,0.15); color:#f87171;'}">
                                ${h.status}
                            </span>
                        </td>
                    </tr>
                `).join('');
            } catch (e) { console.error(e); }
        }

        async function loadSettings() {
            try {
                const res = await fetch('/api/settings');
                const cfg = await res.json();
                document.getElementById('s_api_id').value = cfg.api_id || '';
                document.getElementById('s_api_hash').value = cfg.api_hash || '';
                document.getElementById('s_admin_id').value = cfg.admin_user_id || '';
                document.getElementById('s_conv_bot').value = cfg.default_converter_bot || '';
                document.getElementById('s_timeout').value = cfg.bot_convert_timeout || 25;
                document.getElementById('s_buffer').value = cfg.album_buffer_time || 2.0;
                document.getElementById('s_session').value = cfg.string_session || '';
            } catch (e) { console.error(e); }
        }

        async function saveSettings() {
            const payload = {
                api_id: parseInt(document.getElementById('s_api_id').value),
                api_hash: document.getElementById('s_api_hash').value,
                admin_user_id: parseInt(document.getElementById('s_admin_id').value),
                default_converter_bot: document.getElementById('s_conv_bot').value,
                bot_convert_timeout: parseInt(document.getElementById('s_timeout').value),
                album_buffer_time: parseFloat(document.getElementById('s_buffer').value),
                string_session: document.getElementById('s_session').value
            };
            const res = await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            const statusEl = document.getElementById('settings-status');
            statusEl.innerText = '✅ Saved to MongoDB successfully!';
            setTimeout(() => { statusEl.innerText = ''; }, 4000);
        }

        async function toggleRoute(id) {
            await fetch(`/api/mappings/${id}/toggle`, { method: 'POST' });
            loadStats();
        }

        async function deleteRoute(id) {
            if (confirm('Are you sure you want to delete this channel route?')) {
                await fetch(`/api/mappings/${id}`, { method: 'DELETE' });
                loadMappings();
                loadStats();
            }
        }

        function toggleAdvanced() {
            const body = document.getElementById('advanced-fields');
            const arrow = document.getElementById('acc-arrow');
            if (body.style.display === 'block') {
                body.style.display = 'none';
                arrow.innerText = '▼';
            } else {
                body.style.display = 'block';
                arrow.innerText = '▲';
            }
        }

        function openAddModal() { 
            document.getElementById('addModal').style.display = 'flex'; 
            if (!cachedChannels.length) loadUserChannels();
        }
        function closeAddModal() { document.getElementById('addModal').style.display = 'none'; }

        async function saveNewRoute() {
            const wmOld = document.getElementById('m_wm_old').value.trim();
            const wmNew = document.getElementById('m_wm_new').value.trim();
            const replacements = {};
            if (wmOld) replacements[wmOld] = wmNew;

            const btnText = document.getElementById('m_btn_text').value.trim();
            const buttons = [];
            if (btnText) {
                buttons.push({ text: btnText, type: 'converted_url' });
            }

            const payload = {
                name: document.getElementById('m_name').value || 'New Custom Route',
                source_channel: document.getElementById('m_source').value,
                target_channel: document.getElementById('m_target').value,
                converter_bot: document.getElementById('m_bot').value,
                header_text: document.getElementById('m_header').value,
                footer_text: document.getElementById('m_footer').value,
                watermark_replacements: replacements,
                inline_buttons: buttons,
                strip_unconverted: document.getElementById('m_strip').checked,
                post_delay_seconds: parseInt(document.getElementById('m_delay').value) || 2,
                enabled: true
            };

            if (!payload.source_channel || !payload.target_channel) {
                alert('Both Source Channel and Target Channel are required!');
                return;
            }

            await fetch('/api/mappings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            closeAddModal();
            loadMappings();
            loadStats();
        }

        // Init
        loadStats();
        loadMappings();
        loadUserChannels();
        setInterval(loadStats, 10000);
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(verify_credentials)])
def get_dashboard():
    return DASHBOARD_HTML
