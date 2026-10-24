# A2A Invoice Agent — assignment starter v2

This is an editable FastAPI starter for the synthetic IITM invoice-agent assignment. It adds a Gemini API integration and per-package content cache. **It is not certified as a complete 4/4 solution**: hidden document schemas and protocol/lifecycle edge cases must be verified against grader feedback. Do not spend the final Check/Save until testing is complete.

## 1. Free AI setup

1. Visit https://aistudio.google.com/ and check whether free API access is available for your account and the selected model. Quotas and availability can change.
2. Create an API key. Keep it secret; never put it in GitHub or this chat.

## 2. Run on Windows

Extract the ZIP, open this folder in VS Code, then in PowerShell run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GEMINI_API_KEY="YOUR_GOOGLE_AI_STUDIO_KEY"
$env:A2A_BEARER_TOKEN="THE_TOKEN_EXPECTED_BY_YOUR_ASSIGNMENT"
$env:DATABASE_PATH="invoice_tasks.sqlite3"
$env:A2A_BASE_URL="https://YOUR-RENDER-SERVICE.onrender.com/a2a/"
uvicorn main:app --reload
```

Open http://127.0.0.1:8000/.well-known/agent-card.json to inspect the card. Localhost is for debugging only; the submitted base URL must be public HTTPS.

## 3. Deploy on Render

1. Upload these files to GitHub. Do not upload `.env`, database files, or API keys.
2. Create a Render Web Service connected to the repository.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables in Render: `A2A_BASE_URL`, `A2A_BEARER_TOKEN`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `DATABASE_PATH`.
6. Configure durable storage. For SQLite, attach a persistent disk if supported by your plan and set `DATABASE_PATH` to a file under its mount path. Otherwise use a persistent database service. Ephemeral local storage may lose tasks and cache after restart.
7. Redeploy and check that the Agent Card's `supportedInterfaces[0].url` exactly matches the base URL you submit.

## Endpoints implemented in this scaffold

- `GET /.well-known/agent-card.json`
- `POST /a2a/message:send`
- `GET /a2a/tasks`
- `GET /a2a/tasks/{id}`
- `POST /a2a/tasks/{id}:cancel`

Protected routes expect `Authorization: Bearer ...` and `A2A-Version: 1.0`; message send also expects `Content-Type: application/a2a+json`.

## Required verification before Check or Save

- Confirm actual package ID and document fields in the assignment input; code currently accepts `packageId`, `package_id`, or `id`.
- Validate the Gemini model is available and free-tier quota applies to your account. A request may fail if quota/model access is unavailable.
- Confirm exact A2A 1.0 Task/Message/Part ProtoJSON shapes, HTTP status codes, media types, and response-size limit against the official contract.
- Confirm the grader's expected authentication token scheme. This scaffold configures one token; if the grader expects multiple valid principals, implement that scheme without treating all tokens as the same user.
- Verify continuation replay returns the original completed Task when required, and test concurrent result/cancel operations. These race/idempotency cases are not fully certified by this starter.
- Check that all 3 references are exactly the decisive bracketed references and that action/facts/rationale match the actual documents. Structural validation cannot guarantee model reasoning is correct.
- Confirm every request finishes within 45 seconds and response JSON stays under 512 KiB.
- Do not use real invoice data, payment APIs, or production secrets. The agent only proposes actions and records receipts; it does not pay invoices.

## Assignment check budget

The assignment says each Check or Save consumes one of 10 checks and the last is reserved for Save. Do local testing first; never use Save until the public deployment and lifecycle have been verified.
