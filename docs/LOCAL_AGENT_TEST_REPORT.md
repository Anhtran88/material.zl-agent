# Local Agent / MCP / 9Router integration report — 2026-10-11

Status: code implemented; Linux integration validated; Windows/user-session live acceptance pending. M1 remains NOT ACCEPTED, no M2–M9 implementation.

## Results
53/53 automated tests passed with optional real 9Router integration enabled. Existing 17 PoC/schema checks retained. Added API/credential/gateway controls, Chromium offline DOM/source fixtures, real browser control-page flow (pairing, token removal from URL, local connect, DOM export, secret input cleared/redacted, disconnect), real stdio MCP client against authenticated loopback API, and the pinned 9Router standalone process bootstrap/restart test.

Test invocation:

```
ZMA_ROUTER_TEST_SERVER=/workspace/work/9router-review/package/app/custom-server.js PYTHONPATH=src python -m unittest discover -s tests -v
```

Real 9Router 0.5.99 started on a separate loopback test port, authenticated with generated owner credentials, persisted hashed password/settings, created app API key and dashboard session, served /v1/models with that key and restarted with the same key. No external provider enrolled, no completion requested, no Zalo content sent. Provider count was zero while the catalog exposed 814 models: catalog availability is explicitly NOT AI readiness.

MCP protocol test enumerated exactly five tools and demonstrated refused read before local enable, read after local enable, gateway status and disconnection. UI test verified download of a JSON report through Chromium and no frontend key reflection/localStorage credential persistence. Fixed CSP-sensitive test waiting by using DOM locator assertions; did not weaken production CSP.

Python compilation, JavaScript syntax checks and git diff whitespace checks passed. Wheel build included UI asset and agent/bridge/runtime modules. GitHub Actions config adds Ubuntu/Windows tests plus native PowerShell parser check; no successful CI run or Windows result claimed in this report.

## Limits and remaining approvals
- Automated bootstrap cannot run on the user's Windows machine from this cloud chat. Operator runs the updated local launcher once.
- Windows DPAPI/ACL/PowerShell/portable Node launcher and headful provider dashboard need actual Windows confirmation. Linux credential tests use user-only 0600 file protection, not simulated DPAPI.
- User must authorize a provider/account/terms/costs in the isolated 9Router dashboard; no provider signup, OAuth approval or paid/free availability assumed. Completion/extraction is gated.
- Attach MCP to a compatible LOCAL client if direct tool control is desired. This chat has no automatically attached remote endpoint. No public tunnel or full desktop control is implemented.
- Actual Zalo selectors are partial user observations, not stable contracts. Sender/time, full file/image coverage, history scrolling, original download and read-only network audit remain M1 live gates. Captures stay RAW_UNVERIFIED and never advance accounting/checkpoint.
- Disconnection blocks new work immediately; an already executing DOM snapshot can finish before the endpoint completes. Source/UI/challenge failure revokes the local read enable until local reconnection.
