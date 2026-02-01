from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

app = FastAPI(title="SAFE-LOOP Orchestrator", version="0.5.0")

# ---------------------------
# 1. CORS & Middleware
# ---------------------------
# Allows your local frontend (e.g., Live Server on port 5500) to talk to this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify ["https://safeloop.rrc.ca"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve UI under /ui
app.mount("/ui", StaticFiles(directory="web", html=True), name="web")


# ---------------------------
# 2. Models
# ---------------------------
class CreateSessionIn(BaseModel):
    user_id: str = Field(min_length=3)
    persona: Literal["student", "industry_observer", "indigenous_partner", "instructor"] = "student"
    scenario_id: str = Field(min_length=1)


class CreateSessionOut(BaseModel):
    session_id: str
    status: str


class EthicsDeclarationIn(BaseModel):
    acknowledge_no_harm: bool
    acknowledge_no_real_data: bool
    acknowledge_audit_logging: bool
    acknowledge_professional_codes: bool


class ActionLogIn(BaseModel):
    action_type: str = Field(..., description="Must be 'ethical' or 'exploit'")
    details: dict = Field(default_factory=dict)
    intent: str = Field(default="Simulation Decision")
    expected_impact: str = Field(default="Unknown")


class ReflectionIn(BaseModel):
    what_happened: str = Field(min_length=10)
    who_could_be_harmed: str = Field(min_length=10)
    what_you_would_do_in_industry: str = Field(min_length=10)


# ---------------------------
# 3. In-memory store (Sprint)
# ---------------------------
# Note: Data is lost on server restart. Use Redis for production.
SESSIONS: dict[str, dict] = {}

# Impact Logic Configuration
SCENARIO_IMPACTS = {
    "ethical": {"trust": 10, "streak": 1, "privacy_exposure": -5, "community_harm": -5},
    "exploit": {"trust": -20, "streak": -100, "privacy_exposure": 15, "community_harm": 10},
}


# ---------------------------
# 4. Helpers
# ---------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_user(user_id: str) -> str:
    """Anonymize user email for privacy compliance."""
    return hashlib.sha256(user_id.encode()).hexdigest()[:12]


def baseline_impact() -> dict:
    return {
        "privacy_exposure": 0,
        "trust": 100,
        "regulatory_scrutiny": 0,
        "business_impact": 0,
        "community_harm": 0,
        "updated_at": now_iso(),
    }


def clamp(v: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, v))


def risk_level(impact: dict) -> str:
    score = (
        impact.get("privacy_exposure", 0) * 2
        + impact.get("community_harm", 0) * 2
        + (100 - impact.get("trust", 100))
    ) // 5
    score = clamp(int(score), 0, 100)
    if score >= 60:
        return "High"
    if score >= 30:
        return "Medium"
    return "Low"


def fake_llm_summary(session: dict) -> dict:
    impact = session["impact"]
    actions = session.get("actions", [])
    
    # Get last 3 actions
    last_actions = [a["action_type"] for a in actions[-3:]] if actions else []

    trust = int(impact.get("trust", 100))
    level = risk_level(impact)

    # Determine "Tone" based on Trust Score
    negative = trust < 70

    headline = "⚠️ Critical Risk Assessment" if negative else "✅ Responsible Operation Summary"

    if negative:
        human_impact = (
            "Recent decisions have prioritized speed or curiosity over safety. "
            "In a real-world setting, this would trigger a compliance audit and potentially harm vulnerable user groups."
        )
        recommended = [
            "Review the 'Code of Ethics' immediately.",
            "Reset the simulation and attempt the 'Ethical' path to observe the difference.",
            "Document why you chose the exploit path in your reflection log.",
        ]
    else:
        human_impact = (
            "You have consistently prioritized stakeholder safety. "
            "This builds long-term resilience and trust, even if it requires more initial effort."
        )
        recommended = [
            "Continue applying the 'Do No Harm' principle.",
            "Consider how these safeguards might scale to larger systems.",
            "Prepare your final reflection report."
        ]

    return {
        "headline": headline,
        "risk_level": level,
        "observations": last_actions,
        "human_impact": human_impact,
        "recommended_next_steps": recommended,
        "generated_at": now_iso(),
    }


# ---------------------------
# 5. Routes
# ---------------------------
@app.get("/")
def read_root():
    return RedirectResponse(url="/ui/")
    
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/sessions", response_model=CreateSessionOut)
def create_session(payload: CreateSessionIn) -> CreateSessionOut:
    session_id = str(uuid4())
    
    # Privacy: Store hashed ID
    safe_user_id = hash_user(payload.user_id)

    SESSIONS[session_id] = {
        "user_id": safe_user_id,
        "persona": payload.persona,
        "scenario_id": payload.scenario_id,
        "status": "created",
        "ethics_declared": False,
        "impact": baseline_impact(),
        "actions": [],
        "reflections": [],
    }
    return CreateSessionOut(session_id=session_id, status="created")


@app.post("/sessions/{session_id}/declare_ethics")
def declare_ethics(session_id: str, payload: EthicsDeclarationIn) -> dict:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not (payload.acknowledge_no_harm and payload.acknowledge_no_real_data):
        raise HTTPException(status_code=400, detail="Core ethics must be acknowledged")

    session["ethics_declared"] = True
    session["status"] = "active"
    return {"status": "active", "ethics_declared": True}


@app.post("/sessions/{session_id}/log_action")
def log_action(session_id: str, payload: ActionLogIn) -> dict:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session["ethics_declared"]:
        raise HTTPException(status_code=403, detail="Ethics declaration required")

    impact = session["impact"]
    decision_type = payload.action_type.lower()
    
    # Lookup impact based on decision type (Ethical vs Exploit)
    deltas = SCENARIO_IMPACTS.get(decision_type, {"trust": 0})

    # Apply Deltas
    impact["trust"] = clamp(impact["trust"] + deltas.get("trust", 0))
    impact["privacy_exposure"] = clamp(impact["privacy_exposure"] + deltas.get("privacy_exposure", 0))
    impact["community_harm"] = clamp(impact["community_harm"] + deltas.get("community_harm", 0))
    impact["updated_at"] = now_iso()

    session["actions"].append({
        "ts": now_iso(),
        "action_type": decision_type,
        "details": payload.details,
        "impact_after": dict(impact)
    })
    
    return {"ok": True, "impact": impact}


@app.get("/sessions/{session_id}/llm_summary")
def llm_summary(session_id: str) -> dict:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return fake_llm_summary(session)


@app.post("/sessions/{session_id}/reset")
def reset(session_id: str) -> dict:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session["status"] = "created"
    session["actions"] = []
    session["reflections"] = []
    session["impact"] = baseline_impact()
    return {"ok": True, "status": "reset"}