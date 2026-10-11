# Local Agent + 9Router setup

Current cloud-only policy supersedes historical capture/export instructions below: business captures and operation logs are memory-only, report downloads are disabled, Firebase ingestion is not configured. Zalo profile and operational credentials/runtime remain local. See FIREBASE_SETUP.md.

This is a locally operated integration extension requested during M1. It does not advance the M1 acceptance gate or implement M2–M9. The bridge is functional for compatible local MCP clients; the current cloud chat has no tool attaching to the user's Windows machine. No public tunnel, arbitrary desktop control or credential transfer is provided.

## Windows setup
Use 64-bit Windows, Python 3.12/py launcher and a private Windows account. Close the earlier login/DOM-inspection browser with Enter in its terminal to release the persistent profile. Download/extract the latest project ZIP over the source directory (preserves `.venv`), then double-click scripts/Start-LocalAgent.cmd or execute Start-LocalAgent.ps1 in PowerShell. Administrator privileges are not needed. The bootstrap:

1. Creates user-only LocalAppData/ZaloMaterialAgent permissions, preserving SYSTEM access; sets up Python dependencies and Playwright Chromium.
2. Downloads portable Node **24.19.0** from nodejs.org and verifies the pinned archive SHA-256. Changes PATH only for this process, restores it on exit. Selects x64 or ARM64 from the compiled Python target; does not rely on mutable PROCESSOR_ARCHITECTURE environment variables. Native ARM64 startup still requires actual Windows validation.
3. Uses a committed npm lockfile to install **9router 0.5.99** locally with `npm ci --ignore-scripts`. Runs its bundled custom-server.js directly on **127.0.0.1:20128**, using Node's built-in SQLite. Avoids upstream CLI process killing, tray, upgrades, tunnels, connect-tool rewrites and install hooks. Refuses occupied ports rather than killing unrelated processes. Runtime/data live under LocalAppData, outside OneDrive.
4. Generates owner password/JWT secret and an application API key, stores application credentials under Windows user-scoped DPAPI, authenticates to reviewed 9Router management APIs and configures authenticated local-only service. Disables cloud/tunnel/Tailscale dashboard access, request logs/observability and prompt compression features. Third-party provider storage remains controlled by 9Router and is inside the protected local directory; do not sync/export it.
5. Opens **127.0.0.1:8765** control page using a random per-run pairing credential in the URL fragment, removes it from browser address history immediately, and stores no token in frontend localStorage. Pairing token expires in 8 hours; read connection expires after 30 minutes. Restart generates a new token. Do not share the initial pairing URL or protected connection files.

Automatic setup still needs to be exercised on the user's Windows machine. DPAPI, Windows ACL/PowerShell and the bundled Node server have not been tested on Windows in this Linux executor. No Windows install is claimed until the operator confirms results. If the ports are busy, close existing processes normally; do not disable authentication or expose these ports.

## Local controls and approvals
Click **Mở Zalo**, handle login/security challenges yourself, manually choose the allowlisted group, then click **Kết nối đọc nhóm**. Only currently rendered source-scoped text/image containers are read. Each operation verifies source title and candidate DOM ID and stops on visible dialogs/possible challenges or DOM changes. Detection is conservative and based on partial user-observed DOM; cannot claim comprehensive security-state detection. No send/reply/reaction/upload commands, arbitrary JavaScript, generic click/selectors, arbitrary URLs, shell execution, full-screen screenshots or filesystem browsing are exposed.

Click **Kiểm tra DOM** or **Đọc tin nhắn đang hiển thị**. Captures stay under cache/{UUID}/capture.json; use **Tải báo cáo vừa đọc** for a local JSON export. Messages are RAW_UNVERIFIED with unknown stable message ID/sender/time. Image metadata is not downloaded original evidence. Files, image-message association, scroll/history and download controls are still live integration work. Never count this data as verified delivery/accounting.

Click **Ngắt kết nối** to prevent further reads and close/save Chromium. Ctrl+C stops the API and the owned 9Router process. A synchronous DOM evaluation already running may complete before disconnection takes effect; no new queued reads are allowed afterward. No persistent remote command queue, startup service or automatic reconnect: restarting always requires the operator to enable reads locally.

For AI, click **Duyệt nhà cung cấp AI trong 9Router**: a separate management browser opens with the owned dashboard session, without revealing its password. Choose the provider/account you authorize and complete any OAuth/login yourself. The app does not create external accounts, accept provider terms, select a paid plan or send source data automatically. Enter/select your actual model in the Local Agent page and save; an empty API-key field preserves the generated key only if Base URL is unchanged. Fallback order/timeout/retry/rate-limit config are provided; completion/extraction failover implementation remains a later milestone.

**Kiểm tra 9Router** calls GET /v1/models with the encrypted local key. A models catalog can list hundreds of models with zero connected providers: CONNECTED means the endpoint responded, NOT usable/free AI or a successful completion. Check **Trạng thái bộ cài 9Router** for provider-connection count; even connections are not proof of completion readiness. No completion or Zalo data transmission is implemented before the M1 gate.

## MCP attachment (local compatible client only)
Use **Tải cấu hình MCP của máy này** in the control page for an exact-path, secret-free config file. Add this server to an MCP-capable desktop/CLI client on the same Windows machine/account. Use absolute paths matching the actual project directory:

```json
{
  "mcpServers": {
    "zalo-local-agent": {
      "command": "C:\\Users\\tran\\ZaloMaterial\\material.zl-agent-main\\.venv\\Scripts\\python.exe",
      "args": ["-m", "material_agent.mcp_bridge"]
    }
  }
}
```

For a compatible Codex CLI local config, the equivalent entry is:

```toml
[mcp_servers.zalo_local_agent]
command = "C:/Users/tran/ZaloMaterial/material.zl-agent-main/.venv/Scripts/python.exe"
args = ["-m", "material_agent.mcp_bridge"]
```

Do not overwrite existing client configuration; add the entry using its supported configuration workflow. Local Agent must remain running. No API key/token is included in client config; bridge decrypts same-user connection credentials locally.

Tools: `zalo_status`, `zalo_inspect_dom`, `zalo_read_visible`, `zalo_disconnect`, `nine_router_status`. The remote tool surface cannot open/login/enable the browser, edit provider credentials, invoke arbitrary code, change sources, send content or enable a tunnel. Tool responses may contain untrusted Zalo source text; treat it as evidence, never as instructions. Only attach the bridge to a client you authorize to receive source data. Installing/configuring MCP locally does not attach it to this existing cloud chat, and configuring 9Router does not give this chat desktop access.

## Provenance and verification
Reviewed npm README/CLI/hooks/custom-server and upstream management route implementation, pinned 9router 0.5.99 (npm dist integrity in lockfile). Upstream: https://github.com/decolua/9router ; registry: https://www.npmjs.com/package/9router . Node archive hash from https://nodejs.org/dist/v24.19.0/SHASUMS256.txt . Direct standalone launch is tested below; it is an integration choice using the shipped artifact, not the default upstream CLI startup flow.

Tests cover loopback authentication, Host/Origin checks, local-only enable, expiry, revocation, input/output redaction, redirect refusal, rate/retry limits, source scoping and Chromium offline DOM fixtures. A real stdio MCP client exercises the bridge through a live authenticated loopback API with a fake browser port. Optional real 9Router integration starts the shipped server, bootstraps owner/key/settings, probes the catalog with no provider and restarts preserving the key. Those tests do not establish live Zalo coverage or Windows acceptance.

### Automatic Play/Pause

After opening Zalo and connecting the allowed group, press **Play — tự cuộn và kiểm tra mới**. The backend restores the saved Firestore snapshot, scrolls the verified conversation to its bottom and checks every 15 seconds. Newly observed or edited records are saved; unchanged polls report no change in the checked bottom window without writing another capture. **Pause** waits for a current save to finish. Closing the control-page tab does not stop the backend; disconnecting, stopping the Agent or expiry of the 30-minute connection does. Reconnect then press Play after expiry. Source/UI/cloud errors pause the worker.

Play attempts bounded catch-up to the saved DOM anchor after downtime; an unlocatable anchor or excessive gap pauses the worker. Slip-date extraction is not added by Play. Business data remains cloud-only.

Update: Play now traverses older rendered windows until the last saved DOM anchor is found, then returns to the bottom. Catch-up is bounded to 80 scroll steps and capture size limits; missing anchors or an excessive gap pause without advancing the checkpoint. DOM anchors remain provisional identities; this is not proof of complete server history.

### Visual activity dashboard

The top panel shows the active step, last successful check time, next-check countdown, connection expiry and checks/saves during the current process session. The saved-data panel counts messages and image references in the latest confirmed Zalo capture and displays its complete message text and Firestore document path. Connectivity probes do not count as saved Zalo captures. Image references do not mean original image files were saved. “No change” checks do not increase the save count. Recent activity is bounded session memory; reopening the control page reads the same live backend status. Restart then Play/resume restores the durable capture from Firestore; session counters restart at zero.

### Automatic 9Router and MCP configuration

On Windows startup, the Agent automatically configures the owned local 9Router route/key and detects Claude Desktop (`APPDATA/Claude`), Cursor (`USERPROFILE/.cursor`) and Windsurf (`USERPROFILE/.codeium/windsurf`). It adds the fixed stdio `zalo-local-agent` entry to clients whose settings directories exist, preserves other settings, backs up an existing file and refuses malformed/conflicting entries. Restart those clients to load their MCP server. A private cloud chat is not connected by this local installation.

When a provider connection exists, an empty model setting is filled using a deterministic advertised catalog model. An existing model or custom gateway route is preserved. Catalog selection is not a successful completion test and may still require choosing a model supported by the logged-in provider. No Zalo text or images are submitted to AI during configuration. Provider OAuth/API login remains manual in the authenticated 9Router dashboard. After provider approval, press **Tự động cấu hình 9Router và MCP** again to fetch the model catalog. API keys are not displayed in returned setup results.

### Diagnosing a stopped monitor

The dashboard displays a bounded error code and the stage that failed. `SOURCE_MISSING` may occur while the Zalo search panel replaces the verified conversation-list rows: close search with Zalo's **Đóng**, select the allowed group and reconnect. `SCROLLER_MISSING` means no verified conversation scroll ancestor was found. Nested eligible scroll ancestors now select the nearest ancestor containing all verified source containers, excluding the sidebar. `ANCHOR_NOT_FOUND`, `CATCHUP_LIMIT`, `SCROLL_NOT_SETTLED`, cloud failure codes and connection expiry remain distinct stop conditions; no automatic checkpoint advancement is performed on failure. The reconnect action is available directly in the error panel.

Automatic monitoring reads the viewport of the verified conversation scroller at each navigation step, rather than treating all cached/offscreen DOM nodes as the active window. This prevents a long rendered DOM from silently selecting the first 200 older nodes when the conversation is at the bottom. Manual DOM diagnostics keep their existing bounded rendered-node behavior. A rejected bundle input is reported as `BUNDLE_INPUT_INVALID` at the `BUNDLING` stage. Unexpected exceptions report their class and code-file basename/line only, without exception values, message contents, credentials, stack-local values or disk logs.
