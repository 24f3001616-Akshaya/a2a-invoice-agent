import os
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from task_store import TaskStore
from decision_engine import propose_batch

BASE_URL = os.getenv("A2A_BASE_URL", "https://your-service.onrender.com/a2a/")
TOKEN = os.getenv("A2A_BEARER_TOKEN", "")
DB_PATH = os.getenv("DATABASE_PATH", "invoice_tasks.sqlite3")
store = TaskStore(DB_PATH)
app = FastAPI(title="A2A Invoice Agent")

CARD = {
    "name": "Invoice Action Agent",
    "description": "Evidence-based invoice action proposal agent",
    "version": "1.0.0",
    "capabilities": {},
    "supportedInterfaces": [
        {"url": BASE_URL, "protocolBinding": "HTTP+JSON", "protocolVersion": "1.0"}
    ],
    "defaultInputModes": ["application/vnd.ga5.invoice-claim-batch+json"],
    "defaultOutputModes": [
        "application/vnd.ga5.invoice-action-proposals+json",
        "application/vnd.ga5.invoice-action-receipts+json"
    ],
    "skills": [{
        "id": "invoice_action_agent",
        "name": "Invoice Action Agent",
        "description": "Proposes evidence-backed invoice actions and safely records accepted receipts",
        "tags": ["invoice", "evidence", "approval", "receipt"]
    }]
}

@app.get("/.well-known/agent-card.json")
def agent_card():
    return JSONResponse(CARD, media_type="application/json")

def require_protocol(a2a_version: str | None, content_type: str | None):
    if a2a_version != "1.0":
        raise HTTPException(status_code=400, detail="Unsupported or missing A2A-Version")
    if not content_type or content_type.split(";")[0].strip() != "application/a2a+json":
        raise HTTPException(status_code=415, detail="Unsupported media type")

def require_auth(authorization: str | None):
    if not TOKEN:
        print("AUTH CHECK: A2A_BEARER_TOKEN is empty")
        raise HTTPException(
            status_code=503,
            detail="Service authentication is not configured"
        )

    expected = f"Bearer {TOKEN}"

    if authorization != expected:
        print(
            "AUTH CHECK: token mismatch; "
            f"configured_length={len(TOKEN)}, "
            f"received_header_present={authorization is not None}, "
            f"received_bearer_prefix={authorization.startswith('Bearer ') if authorization else False}"
        )
        raise HTTPException(status_code=401, detail="Unauthorized")

    return TOKEN

def a2a_response(task):
    return JSONResponse({"task": task}, media_type="application/a2a+json")

@app.post("/a2a/message:send")
async def send_message(request: Request, authorization: str | None = Header(None),
                       a2a_version: str | None = Header(None, alias="A2A-Version"),
                       content_type: str | None = Header(None, alias="Content-Type")):
    principal = require_auth(authorization)
    require_protocol(a2a_version, content_type)
    body = await request.json()
    msg = body.get("message")
    if not isinstance(msg, dict) or not msg.get("messageId"):
        raise HTTPException(status_code=400, detail="Invalid message envelope")
    try:
        existing = store.lookup_message(principal, msg["messageId"], msg)
        if existing:
            return a2a_response(existing)
        parts = msg.get("parts", [])
        data_part = next((p for p in parts if isinstance(p, dict) and "data" in p), None)
        if not data_part:
            raise HTTPException(status_code=400, detail="Missing message data")
        media = data_part.get("mediaType", "")
        data = data_part.get("data", {})
        if media == "application/vnd.ga5.invoice-claim-batch+json":
            proposals = propose_batch(data)
            task_id = store.new_id()
            context_id = msg.get("contextId") or store.new_id()
            task = {
                "id": task_id, "contextId": context_id, "status": {"state": "TASK_STATE_INPUT_REQUIRED"},
                "history": [msg], "artifacts": [{
                    "artifactId": store.new_id(),
                    "parts": [{"mediaType": "application/vnd.ga5.invoice-action-proposals+json",
                               "data": proposals}]
                }],
                "metadata": {"principal": principal, "batchId": data.get("batchId")}
            }
            store.create_task(principal, msg["messageId"], msg, task)
            return a2a_response(task)
        elif media == "application/vnd.ga5.invoice-action-results+json":
            task_id = msg.get("taskId")
            task = store.get_task(principal, task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            if msg.get("contextId") != task.get("contextId"):
                raise HTTPException(status_code=400, detail="Task context mismatch")
            result_data = data
            batch_id = task.get("metadata", {}).get("batchId")
            if result_data.get("batchId") != batch_id:
                raise HTTPException(status_code=400, detail="Batch mismatch")
            proposal_data = task["artifacts"][0]["parts"][0]["data"]
            proposals = {p["packageId"]: p for p in proposal_data.get("proposals", [])}
            executions = []
            for result in result_data.get("results", []):
                proposal = proposals.get(result.get("packageId"))
                if not proposal:
                    raise HTTPException(status_code=400, detail="Unknown proposal")
                if result.get("actionId") != proposal["actionId"] or result.get("action") != proposal["action"]:
                    raise HTTPException(status_code=400, detail="Proposal mismatch")
                if result.get("outcome") == "ACCEPTED":
                    executions.append({
                        "packageId": proposal["packageId"], "actionId": proposal["actionId"],
                        "action": proposal["action"], "receiptNonce": result.get("receiptNonce"),
                        "facts": proposal["facts"], "evidenceRefs": proposal["evidenceRefs"]
                    })
            task["history"].append(msg)
            task["artifacts"].append({
                "artifactId": store.new_id(),
                "parts": [{"mediaType": "application/vnd.ga5.invoice-action-receipts+json",
                           "data": {"batchId": batch_id, "executions": executions}}]
            })
            task["status"] = {"state": "TASK_STATE_COMPLETED"}
            store.update_task(principal, task_id, task)
            return a2a_response(task)
        else:
            raise HTTPException(status_code=415, detail="Unsupported input media type")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

@app.get("/a2a/tasks")
def list_tasks(authorization: str | None = Header(None),
               a2a_version: str | None = Header(None, alias="A2A-Version")):
    principal = require_auth(authorization)
    if a2a_version != "1.0":
        raise HTTPException(status_code=400, detail="Unsupported or missing A2A-Version")
    return JSONResponse({"tasks": store.list_tasks(principal)}, media_type="application/a2a+json")

@app.get("/a2a/tasks/{task_id}")
def get_task(task_id: str, authorization: str | None = Header(None),
             a2a_version: str | None = Header(None, alias="A2A-Version"),
             content_type: str | None = Header(None, alias="Content-Type")):
    principal = require_auth(authorization)
    if a2a_version != "1.0":
        raise HTTPException(status_code=400, detail="Unsupported or missing A2A-Version")
    task = store.get_task(principal, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return JSONResponse(task, media_type="application/a2a+json")

@app.post("/a2a/tasks/{task_id}:cancel")
def cancel_task(task_id: str, authorization: str | None = Header(None),
                a2a_version: str | None = Header(None, alias="A2A-Version"),
                content_type: str | None = Header(None, alias="Content-Type")):
    principal = require_auth(authorization)
    if a2a_version != "1.0":
        raise HTTPException(status_code=400, detail="Unsupported or missing A2A-Version")
    task = store.get_task(principal, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("status", {}).get("state") in ("TASK_STATE_COMPLETED", "TASK_STATE_CANCELED"):
        raise HTTPException(status_code=409, detail="Task is already terminal")
    task["status"] = {"state": "TASK_STATE_CANCELED"}
    store.update_task(principal, task_id, task)
    return JSONResponse(task, media_type="application/a2a+json")
