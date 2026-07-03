"""
Aethvion Suite - Physics & Math Lab Routes

A computational research workbench. The math is REAL — symbolic work is done by
sympy, numerical integration/simulation by scipy, plotting by matplotlib. The AI
layer is optional and only used to (a) turn a natural-language problem into a
formal setup, and (b) interpret results in plain language. It never fabricates
the numbers.

API prefix: /api/physics-lab
"""

import io
import json
import base64
import asyncio
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from core.utils import get_logger

logger = get_logger("web.physics_routes")
router = APIRouter(prefix="/api/physics-lab", tags=["PhysicsLab"])


# ── Lazy, cached heavy imports ────────────────────────────────────────────────
# Imported on first use so a missing scientific dep degrades one endpoint rather
# than killing router registration at startup.
def _sympy():
    import sympy
    return sympy


def _plt():
    import matplotlib
    matplotlib.use("Agg")  # headless — no GUI backend in the server thread
    import matplotlib.pyplot as plt
    return plt


# Palette matched to the dashboard so plots feel native.
_BG = "#0d0e16"
_FG = "#f4f6fb"
_GRID = "#2a2b38"
_ACCENT = "#22d3ee"
_ACCENT2 = "#a78bfa"
_SERIES = ["#22d3ee", "#a78bfa", "#4ade80", "#fb923c", "#f472b6", "#60a5fa"]


def _style_axes(fig, ax):
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_BG)
    for spine in ax.spines.values():
        spine.set_color(_GRID)
    ax.tick_params(colors=_FG, labelsize=8)
    ax.grid(True, color=_GRID, linewidth=0.6, alpha=0.6)
    ax.xaxis.label.set_color(_FG)
    ax.yaxis.label.set_color(_FG)
    ax.title.set_color(_FG)


def _fig_to_b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("ascii")
    _plt().close(fig)
    return "data:image/png;base64," + b64


def _parse(expr_str: str, sympy):
    """Parse a user expression with implicit multiplication (2x -> 2*x) and
    caret power (x^2 -> x**2), which is what people actually type."""
    # NOTE: `implicit_multiplication` (not `..._application`) is deliberate — the
    # `_application` variant bundles `split_symbols`, which shreds multi-char names
    # like `y1` into `y*1`. We keep implicit `2x -> 2*x` but preserve `y1`, `x0`, …
    from sympy.parsing.sympy_parser import (
        parse_expr, standard_transformations,
        implicit_multiplication, convert_xor,
    )
    transformations = standard_transformations + (
        implicit_multiplication, convert_xor,
    )
    return parse_expr(expr_str, transformations=transformations, evaluate=True)


def _both_forms(sympy, expr):
    """Return LaTeX + a plain unicode rendering for any sympy object."""
    try:
        latex = sympy.latex(expr)
    except Exception:
        latex = ""
    try:
        text = sympy.pretty(expr, use_unicode=True)
    except Exception:
        text = str(expr)
    return latex, text


# ── Symbolic engine ───────────────────────────────────────────────────────────
class SymbolicRequest(BaseModel):
    expression: str
    operation: str = "simplify"   # simplify|expand|factor|solve|derivative|integral|limit|roots|evaluate
    variable: str = "x"
    # operation-specific extras
    point: Optional[str] = None   # for limit / evaluate
    order: int = 1                # for derivative


@router.post("/symbolic")
async def symbolic(req: SymbolicRequest):
    return await asyncio.to_thread(_symbolic_impl, req)


def _symbolic_impl(req: SymbolicRequest) -> Dict[str, Any]:
    try:
        sympy = _sympy()
        var = sympy.Symbol(req.variable)
        op = req.operation

        # An '=' means an equation. For solve/roots build Eq(lhs, rhs); for any
        # other op collapse it to (lhs - rhs) so simplify/factor/etc still work.
        if "=" in req.expression:
            lhs_s, rhs_s = req.expression.split("=", 1)
            lhs, rhs = _parse(lhs_s, sympy), _parse(rhs_s, sympy)
            expr = sympy.Eq(lhs, rhs) if op in ("solve", "roots") else (lhs - rhs)
        else:
            expr = _parse(req.expression, sympy)

        steps = []

        if op == "simplify":
            result = sympy.simplify(expr)
        elif op == "expand":
            result = sympy.expand(expr)
        elif op == "factor":
            result = sympy.factor(expr)
        elif op == "solve":
            sols = sympy.solve(expr, var, dict=False)
            result = sols
            steps = [f"{req.variable} = {sympy.nsimplify(s) if s.is_number else s}"
                     for s in (sols if isinstance(sols, list) else [sols])]
        elif op == "roots":
            sols = sympy.solve(expr, var)
            result = sols
        elif op == "derivative":
            result = sympy.diff(expr, var, req.order)
        elif op == "integral":
            result = sympy.integrate(expr, var)
        elif op == "limit":
            pt = _parse(req.point or "0", sympy)
            result = sympy.limit(expr, var, pt)
        elif op == "evaluate":
            if req.point:
                pt = _parse(req.point, sympy)
                result = expr.subs(var, pt)
            else:
                result = expr
            result = sympy.N(result)
        else:
            return {"ok": False, "error": f"Unknown operation: {op}"}

        latex, text = _both_forms(sympy, result)

        # Numeric value when the result is (or reduces to) a number
        numeric = None
        try:
            if hasattr(result, "free_symbols") and not result.free_symbols:
                numeric = float(sympy.N(result))
        except Exception:
            numeric = None

        return {
            "ok": True,
            "operation": op,
            "latex": latex,
            "text": text,
            "result_str": str(result),
            "numeric": numeric,
            "steps": steps,
        }
    except Exception as exc:
        logger.warning("symbolic op failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── Function plotter ──────────────────────────────────────────────────────────
class PlotRequest(BaseModel):
    expressions: List[str]        # one or more f(x)
    variable: str = "x"
    x_min: float = -10.0
    x_max: float = 10.0
    points: int = 400
    title: Optional[str] = None


@router.post("/plot")
async def plot(req: PlotRequest):
    return await asyncio.to_thread(_plot_impl, req)


def _plot_impl(req: PlotRequest) -> Dict[str, Any]:
    try:
        import numpy as np
        sympy = _sympy()
        plt = _plt()

        var = sympy.Symbol(req.variable)
        xs = np.linspace(req.x_min, req.x_max, max(50, min(req.points, 5000)))

        fig, ax = plt.subplots(figsize=(7, 4.2))
        _style_axes(fig, ax)

        plotted = 0
        for i, expr_s in enumerate(req.expressions):
            expr_s = expr_s.strip()
            if not expr_s:
                continue
            expr = _parse(expr_s, sympy)
            f = sympy.lambdify(var, expr, modules=["numpy"])
            with np.errstate(all="ignore"):
                ys = f(xs)
            ys = np.asarray(ys, dtype="float64")
            ys[~np.isfinite(ys)] = np.nan
            ax.plot(xs, ys, color=_SERIES[i % len(_SERIES)], linewidth=2,
                    label=f"{req.variable} → {expr_s}")
            plotted += 1

        if plotted == 0:
            return {"ok": False, "error": "No valid expressions to plot."}

        ax.axhline(0, color=_GRID, linewidth=1)
        ax.axvline(0, color=_GRID, linewidth=1)
        ax.set_xlabel(req.variable)
        ax.set_ylabel(f"f({req.variable})")
        if req.title:
            ax.set_title(req.title)
        leg = ax.legend(facecolor=_BG, edgecolor=_GRID, labelcolor=_FG, fontsize=8)
        if leg:
            leg.get_frame().set_alpha(0.85)

        return {"ok": True, "image": _fig_to_b64(fig)}
    except Exception as exc:
        logger.warning("plot failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── ODE simulator (first-order system) ────────────────────────────────────────
class ODERequest(BaseModel):
    # Each equation is the RHS of dy_i/dt = f(t, y0, y1, ...). state_vars names the
    # y_i in order; the independent var is always 't'.
    equations: List[str]
    state_vars: List[str]
    initial: List[float]
    t_min: float = 0.0
    t_max: float = 20.0
    points: int = 500
    params: Optional[Dict[str, float]] = None
    phase: bool = False           # if 2 vars: also draw a phase portrait


@router.post("/ode")
async def ode(req: ODERequest):
    return await asyncio.to_thread(_ode_impl, req)


def _ode_impl(req: ODERequest) -> Dict[str, Any]:
    try:
        import numpy as np
        from scipy.integrate import solve_ivp
        sympy = _sympy()
        plt = _plt()

        n = len(req.state_vars)
        if n == 0:
            return {"ok": False, "error": "No state variables defined."}
        if len(req.equations) != n or len(req.initial) != n:
            return {"ok": False, "error": "equations, state_vars and initial must be the same length."}

        t = sympy.Symbol("t")
        state_syms = [sympy.Symbol(v) for v in req.state_vars]
        param_syms = {k: sympy.Symbol(k) for k in (req.params or {})}
        local_syms = [t] + state_syms + list(param_syms.values())

        rhs_funcs = []
        for eq in req.equations:
            expr = _parse(eq, sympy)
            if req.params:
                expr = expr.subs({param_syms[k]: v for k, v in req.params.items()})
            rhs_funcs.append(sympy.lambdify([t] + state_syms, expr, modules=["numpy"]))

        def system(tv, y):
            return [f(tv, *y) for f in rhs_funcs]

        t_eval = np.linspace(req.t_min, req.t_max, max(50, min(req.points, 5000)))
        sol = solve_ivp(system, (req.t_min, req.t_max), req.initial,
                        t_eval=t_eval, method="RK45", rtol=1e-6, atol=1e-9)

        if not sol.success:
            return {"ok": False, "error": f"Integration failed: {sol.message}"}

        # Time-series plot
        fig, ax = plt.subplots(figsize=(7, 4.2))
        _style_axes(fig, ax)
        for i, name in enumerate(req.state_vars):
            ax.plot(sol.t, sol.y[i], color=_SERIES[i % len(_SERIES)], linewidth=2, label=name)
        ax.set_xlabel("t")
        ax.set_ylabel("state")
        ax.set_title("Time evolution")
        leg = ax.legend(facecolor=_BG, edgecolor=_GRID, labelcolor=_FG, fontsize=8)
        if leg:
            leg.get_frame().set_alpha(0.85)
        time_img = _fig_to_b64(fig)

        phase_img = None
        if req.phase and n >= 2:
            fig2, ax2 = plt.subplots(figsize=(5.2, 4.2))
            _style_axes(fig2, ax2)
            ax2.plot(sol.y[0], sol.y[1], color=_ACCENT, linewidth=1.6)
            ax2.plot([sol.y[0][0]], [sol.y[1][0]], "o", color=_ACCENT2, markersize=6)
            ax2.set_xlabel(req.state_vars[0])
            ax2.set_ylabel(req.state_vars[1])
            ax2.set_title("Phase portrait")
            phase_img = _fig_to_b64(fig2)

        return {
            "ok": True,
            "image": time_img,
            "phase_image": phase_img,
            "final_state": {req.state_vars[i]: float(sol.y[i][-1]) for i in range(n)},
        }
    except Exception as exc:
        logger.warning("ode failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── AI layer (optional) ───────────────────────────────────────────────────────
class FormalizeRequest(BaseModel):
    description: str
    model_id: str = "auto"


_FORMALIZE_SYSTEM = (
    "You are a physics and mathematics research assistant. The user describes a "
    "problem in plain language. Turn it into a precise, formal setup that a "
    "symbolic/numeric engine can run. Be concrete: give exact expressions using "
    "^ for powers and standard function names (sin, cos, exp, log, sqrt). If it "
    "is an ordinary differential equation or a dynamical system, write it as a "
    "first-order system dy_i/dt = f(...). State every parameter value. Do NOT "
    "solve it yourself — the engine does that. Keep it tight."
)

_INTERPRET_SYSTEM = (
    "You are a physics and mathematics research assistant. You are given a "
    "problem setup and the exact result computed by a symbolic/numeric engine. "
    "Explain what the result means physically/mathematically, note any special "
    "behaviour (equilibria, stability, asymptotics, singularities), and keep it "
    "rigorous and concise. The numbers are correct — interpret, do not recompute."
)


def _stream_llm(prompt: str, system: str, model_id: str, trace_prefix: str):
    async def event_generator():
        try:
            from core.providers.provider_manager import get_provider_manager
            from core.ai.call_contexts import CallSource

            pm = get_provider_manager()
            trace_id = f"{trace_prefix}-{uuid.uuid4().hex[:8]}"
            full_prompt = f"{system}\n\n=== INPUT ===\n{prompt}\n\nResponse:"

            def _call():
                return pm.call_with_failover(
                    prompt=full_prompt,
                    trace_id=trace_id,
                    temperature=0.3,
                    model=model_id,
                    request_type="generation",
                    source=CallSource.RESEARCH,
                )

            response = await asyncio.to_thread(_call)
            if not response.success:
                yield f"data: {json.dumps({'error': response.error or 'LLM call failed'})}\n\n"
                return

            text = response.content or ""
            for i in range(0, len(text), 8):
                yield f"data: {json.dumps({'token': text[i:i + 8]})}\n\n"
                await asyncio.sleep(0.01)
            yield f"data: {json.dumps({'done': True, 'model': response.model})}\n\n"
        except Exception as exc:
            logger.error("physics-lab LLM error: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/formalize")
async def formalize(req: FormalizeRequest):
    return _stream_llm(req.description, _FORMALIZE_SYSTEM, req.model_id, "physics-formalize")


class InterpretRequest(BaseModel):
    context: str
    model_id: str = "auto"


@router.post("/interpret")
async def interpret(req: InterpretRequest):
    return _stream_llm(req.context, _INTERPRET_SYSTEM, req.model_id, "physics-interpret")


# convenient alias so server.py can register `physics_router`
physics_router = router
