import os
import sys
import json
import uuid
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

# ---------------------------------------------------------------------------
# Bootstrap workspace root & imports
# ---------------------------------------------------------------------------
WORKSPACE_ROOT = Path(__file__).parent.parent.parent
sys.path.append(str(WORKSPACE_ROOT))
from core.utils.port_manager import PortManager
from core.utils import get_logger

logger = get_logger("AethvionFinance")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Aethvion Finance — Financial Hub",
    description="Professional Financial Tracking & Analysis",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------
APP_DIR = Path(__file__).parent
DATA_DIR = WORKSPACE_ROOT / "data" / "finance"
PROJECTS_DIR = DATA_DIR / "projects"
AUTOSAVE_PATH = DATA_DIR / "autosave.aethfinance"

for d in [DATA_DIR, PROJECTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Static files & HTML serving
# ---------------------------------------------------------------------------
VIEWER_DIR = APP_DIR / "viewer"

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = VIEWER_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Aethvion Finance</h1><p>Viewer not found.</p>", status_code=404)

if VIEWER_DIR.exists():
    for sub in ["css", "js"]:
        (VIEWER_DIR / sub).mkdir(parents=True, exist_ok=True)
    app.mount("/js", StaticFiles(directory=str(VIEWER_DIR / "js")), name="js")
    app.mount("/css", StaticFiles(directory=str(VIEWER_DIR / "css")), name="css")

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.utcnow().isoformat()

def _make_default_state() -> dict:
    return {
        "meta": {
            "name": "My Finances",
            "currency": "€",
            "created": _now_iso(),
            "modified": _now_iso(),
        },
        "accounts": [],
        "transactions": [],
        "budgets": [],
        "goals": [],
        "holdings": [],
    }

state: dict = _make_default_state()

# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------
def _persist(path: Path, data: dict) -> None:
    """Write state dict to a .aethfinance file (JSON). Called in background thread."""
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        logger.error(f"Persist to {path} failed: {exc}")

def _autosave() -> None:
    """Fire-and-forget autosave in a daemon thread."""
    state["meta"]["modified"] = _now_iso()
    t = threading.Thread(target=_persist, args=(AUTOSAVE_PATH, state), daemon=True)
    t.start()

def _load_from_path(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    # Ensure all top-level keys are present (forward-compat)
    for key in ("meta", "accounts", "transactions", "budgets", "goals", "holdings"):
        if key not in data:
            data[key] = _make_default_state()[key]
    return data

# ---------------------------------------------------------------------------
# Startup: load autosave if it exists
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    global state
    if AUTOSAVE_PATH.exists():
        try:
            state = _load_from_path(AUTOSAVE_PATH)
            logger.info("Loaded autosave state from disk.")
        except Exception as exc:
            logger.warning(f"Could not load autosave ({exc}); starting fresh.")
            state = _make_default_state()
    else:
        state = _make_default_state()
        logger.info("No autosave found; starting with empty state.")

# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------
class TransactionIn(BaseModel):
    name: str
    amount: float
    date: str
    category: str
    type: str          # "income" | "expense"
    account_id: str = ""
    note: str = ""

class TransactionUpdate(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = None
    date: Optional[str] = None
    category: Optional[str] = None
    type: Optional[str] = None
    account_id: Optional[str] = None
    note: Optional[str] = None

class AccountIn(BaseModel):
    name: str
    type: str          # checking / savings / investment / cash
    balance: float = 0.0
    color: str = "#00d2ff"
    note: str = ""

class AccountUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    balance: Optional[float] = None
    color: Optional[str] = None
    note: Optional[str] = None

class BudgetIn(BaseModel):
    category: str
    limit: float
    period: str = "monthly"

class GoalIn(BaseModel):
    name: str
    target: float
    current: float = 0.0
    deadline: str = ""
    color: str = "#00d2ff"
    note: str = ""

class GoalUpdate(BaseModel):
    name: Optional[str] = None
    target: Optional[float] = None
    current: Optional[float] = None
    deadline: Optional[str] = None
    color: Optional[str] = None
    note: Optional[str] = None

class HoldingIn(BaseModel):
    ticker: str
    name: str
    asset_type: str   # stock / etf / crypto / bond / reit / fund / cash / other
    shares: float
    buy_price: float
    current_price: float
    currency: str = "€"
    note: str = ""

class HoldingUpdate(BaseModel):
    ticker: Optional[str] = None
    name: Optional[str] = None
    asset_type: Optional[str] = None
    shares: Optional[float] = None
    buy_price: Optional[float] = None
    current_price: Optional[float] = None
    currency: Optional[str] = None
    note: Optional[str] = None

class SaveRequest(BaseModel):
    name: str

class FullState(BaseModel):
    meta: dict
    accounts: list
    transactions: list
    budgets: list
    goals: list
    holdings: list = []

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    return {"status": "ok"}

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
@app.get("/api/state")
async def get_state():
    return state

@app.post("/api/state")
async def replace_state(new_state: FullState):
    global state
    state = new_state.dict()
    _autosave()
    return state

# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
@app.post("/api/transaction")
async def add_transaction(tx: TransactionIn):
    new_tx = {
        "id": str(uuid.uuid4()),
        "name": tx.name,
        "amount": tx.amount,
        "date": tx.date,
        "category": tx.category,
        "type": tx.type,
        "account_id": tx.account_id,
        "note": tx.note,
    }
    state["transactions"].append(new_tx)
    _autosave()
    return new_tx

@app.put("/api/transaction/{tx_id}")
async def update_transaction(tx_id: str, update: TransactionUpdate):
    for tx in state["transactions"]:
        if tx["id"] == tx_id:
            for field, value in update.dict(exclude_none=True).items():
                tx[field] = value
            _autosave()
            return tx
    raise HTTPException(status_code=404, detail="Transaction not found")

@app.delete("/api/transaction/{tx_id}")
async def delete_transaction(tx_id: str):
    before = len(state["transactions"])
    state["transactions"] = [t for t in state["transactions"] if t["id"] != tx_id]
    if len(state["transactions"]) == before:
        raise HTTPException(status_code=404, detail="Transaction not found")
    _autosave()
    return {"deleted": tx_id}

# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
@app.post("/api/account")
async def add_account(acc: AccountIn):
    new_acc = {
        "id": str(uuid.uuid4()),
        "name": acc.name,
        "type": acc.type,
        "balance": acc.balance,
        "color": acc.color,
        "note": acc.note,
    }
    state["accounts"].append(new_acc)
    _autosave()
    return new_acc

@app.put("/api/account/{acc_id}")
async def update_account(acc_id: str, update: AccountUpdate):
    for acc in state["accounts"]:
        if acc["id"] == acc_id:
            for field, value in update.dict(exclude_none=True).items():
                acc[field] = value
            _autosave()
            return acc
    raise HTTPException(status_code=404, detail="Account not found")

@app.delete("/api/account/{acc_id}")
async def delete_account(acc_id: str):
    before = len(state["accounts"])
    state["accounts"] = [a for a in state["accounts"] if a["id"] != acc_id]
    if len(state["accounts"]) == before:
        raise HTTPException(status_code=404, detail="Account not found")
    _autosave()
    return {"deleted": acc_id}

# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------
@app.post("/api/budget")
async def upsert_budget(budget: BudgetIn):
    for b in state["budgets"]:
        if b["category"] == budget.category:
            b["limit"] = budget.limit
            b["period"] = budget.period
            _autosave()
            return b
    new_budget = {
        "id": str(uuid.uuid4()),
        "category": budget.category,
        "limit": budget.limit,
        "period": budget.period,
    }
    state["budgets"].append(new_budget)
    _autosave()
    return new_budget

@app.delete("/api/budget/{category}")
async def delete_budget(category: str):
    before = len(state["budgets"])
    state["budgets"] = [b for b in state["budgets"] if b["category"] != category]
    if len(state["budgets"]) == before:
        raise HTTPException(status_code=404, detail="Budget not found")
    _autosave()
    return {"deleted": category}

# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------
@app.post("/api/goal")
async def add_goal(goal: GoalIn):
    new_goal = {
        "id": str(uuid.uuid4()),
        "name": goal.name,
        "target": goal.target,
        "current": goal.current,
        "deadline": goal.deadline,
        "color": goal.color,
        "note": goal.note,
    }
    state["goals"].append(new_goal)
    _autosave()
    return new_goal

@app.put("/api/goal/{goal_id}")
async def update_goal(goal_id: str, update: GoalUpdate):
    for g in state["goals"]:
        if g["id"] == goal_id:
            for field, value in update.dict(exclude_none=True).items():
                g[field] = value
            _autosave()
            return g
    raise HTTPException(status_code=404, detail="Goal not found")

@app.delete("/api/goal/{goal_id}")
async def delete_goal(goal_id: str):
    before = len(state["goals"])
    state["goals"] = [g for g in state["goals"] if g["id"] != goal_id]
    if len(state["goals"]) == before:
        raise HTTPException(status_code=404, detail="Goal not found")
    _autosave()
    return {"deleted": goal_id}

# ---------------------------------------------------------------------------
# Holdings (Portfolio)
# ---------------------------------------------------------------------------
@app.post("/api/holding")
async def add_holding(holding: HoldingIn):
    new_holding = {
        "id": str(uuid.uuid4()),
        "ticker": holding.ticker.upper(),
        "name": holding.name,
        "asset_type": holding.asset_type,
        "shares": holding.shares,
        "buy_price": holding.buy_price,
        "current_price": holding.current_price,
        "currency": holding.currency,
        "note": holding.note,
    }
    if "holdings" not in state:
        state["holdings"] = []
    state["holdings"].append(new_holding)
    _autosave()
    return new_holding

@app.put("/api/holding/{holding_id}")
async def update_holding(holding_id: str, update: HoldingUpdate):
    if "holdings" not in state:
        raise HTTPException(status_code=404, detail="Holding not found")
    for h in state["holdings"]:
        if h["id"] == holding_id:
            for field, value in update.dict(exclude_none=True).items():
                if field == "ticker" and value:
                    value = value.upper()
                h[field] = value
            _autosave()
            return h
    raise HTTPException(status_code=404, detail="Holding not found")

@app.delete("/api/holding/{holding_id}")
async def delete_holding(holding_id: str):
    if "holdings" not in state:
        raise HTTPException(status_code=404, detail="Holding not found")
    before = len(state["holdings"])
    state["holdings"] = [h for h in state["holdings"] if h["id"] != holding_id]
    if len(state["holdings"]) == before:
        raise HTTPException(status_code=404, detail="Holding not found")
    _autosave()
    return {"deleted": holding_id}

# ---------------------------------------------------------------------------
# Holdings price refresh (yfinance / Yahoo Finance)
# ---------------------------------------------------------------------------
@app.post("/api/holdings/refresh-prices")
def refresh_holding_prices():
    """
    Fetch latest market prices for all holdings via Yahoo Finance.
    Runs synchronously in FastAPI's thread pool so blocking I/O is safe.
    Crypto tickers like BTC are auto-converted to BTC-USD for Yahoo Finance.
    """
    try:
        import yfinance as yf          # noqa: PLC0415 – lazy import, optional dep
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="yfinance is not installed. Re-run Start_Finance.bat to install it.",
        )

    holdings = state.get("holdings", [])
    if not holdings:
        return {"updated": 0, "skipped": 0, "errors": [], "holdings": []}

    # Build ticker map: holding_id → yf_symbol
    ticker_map: dict = {}
    for h in holdings:
        raw = (h.get("ticker") or "").strip().upper()
        if not raw:
            continue
        asset_type = (h.get("asset_type") or "").lower()
        # Yahoo Finance needs BTC-USD format for crypto
        if asset_type == "crypto" and "-" not in raw and "/" not in raw:
            yf_sym = raw + "-USD"
        else:
            yf_sym = raw.replace("/", "-")   # e.g. "BTC/USD" → "BTC-USD"
        ticker_map[h["id"]] = yf_sym

    if not ticker_map:
        return {"updated": 0, "skipped": len(holdings), "errors": [], "holdings": holdings}

    # Deduplicate symbols for batch download
    unique_syms = list(set(ticker_map.values()))

    # --- Fetch prices ---
    prices: dict = {}
    errors: list = []

    try:
        # yf.Tickers handles multiple symbols efficiently
        batch = yf.Tickers(" ".join(unique_syms))
        for sym in unique_syms:
            try:
                t = batch.tickers[sym]
                price = t.fast_info.last_price
                # fast_info can return None for illiquid / delisted tickers
                if price is None or price <= 0:
                    hist = t.history(period="5d", auto_adjust=True, progress=False)
                    if not hist.empty:
                        price = float(hist["Close"].iloc[-1])
                if price and price > 0:
                    prices[sym] = round(float(price), 8)
                else:
                    errors.append(f"{sym}: no price data returned")
            except Exception as exc:
                errors.append(f"{sym}: {str(exc)[:100]}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Yahoo Finance error: {exc}")

    # --- Apply prices to state ---
    updated = 0
    skipped = 0
    for h in holdings:
        sym = ticker_map.get(h["id"])
        if sym and sym in prices:
            h["current_price"] = prices[sym]
            updated += 1
        else:
            skipped += 1

    if updated > 0:
        _autosave()

    return {
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "holdings": holdings,
    }

# ---------------------------------------------------------------------------
# Project save/load
# ---------------------------------------------------------------------------
@app.post("/api/save")
async def save_project(req: SaveRequest):
    filename = req.name.strip().replace(" ", "_").replace("/", "_").replace("\\", "_")
    if not filename.endswith(".aethfinance"):
        filename += ".aethfinance"
    path = PROJECTS_DIR / filename
    _persist(path, state)
    return {"filename": filename}

@app.get("/api/projects")
async def list_projects():
    projects = []
    for p in sorted(PROJECTS_DIR.glob("*.aethfinance"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            meta = data.get("meta", {})
        except Exception:
            meta = {}
        stats = p.stat()
        projects.append({
            "filename": p.name,
            "name": meta.get("name", p.stem),
            "currency": meta.get("currency", "€"),
            "modified": meta.get("modified", datetime.fromtimestamp(stats.st_mtime).isoformat()),
            "size": stats.st_size,
        })
    return {"projects": projects}

@app.post("/api/load/{filename}")
async def load_project(filename: str):
    global state
    path = PROJECTS_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project file not found")
    try:
        state = _load_from_path(path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse project file: {exc}")
    _autosave()
    return state

@app.delete("/api/projects/{filename}")
async def delete_project(filename: str):
    path = PROJECTS_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project file not found")
    path.unlink()
    return {"deleted": filename}

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
def launch():
    base_port = int(os.getenv("FINANCE_PORT", "8087"))
    port = PortManager.bind_port("Aethvion Finance", base_port)
    logger.info(f"Aethvion Finance → http://localhost:{port}")
    try:
        from core.utils.browser import open_app_window
        open_app_window(f"http://localhost:{port}", delay=1.5)
    except Exception:
        pass
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    launch()
