"""
Aethvion Suite - Data & Statistics Lab Routes

Real statistics — descriptive summaries, hypothesis tests, regression, and
dimensionality reduction/clustering are computed by scipy.stats, numpy and
scikit-learn. The AI layer only recommends an appropriate test for a question
or interprets a computed result; it never invents statistics.

API prefix: /api/stats-lab
"""

import io
import json
import math
import base64
import asyncio
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from core.utils import get_logger

logger = get_logger("web.stats_routes")
router = APIRouter(prefix="/api/stats-lab", tags=["StatsLab"])


# ── Plot styling (matched to the dashboard) ───────────────────────────────────
_BG = "#0d0e16"
_FG = "#f4f6fb"
_GRID = "#2a2b38"
_ACCENT = "#22d3ee"
_ACCENT2 = "#a78bfa"
_SERIES = ["#22d3ee", "#a78bfa", "#4ade80", "#fb923c", "#f472b6", "#60a5fa"]


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _style_axes(fig, ax):
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_BG)
    for spine in ax.spines.values():
        spine.set_color(_GRID)
    ax.tick_params(colors=_FG, labelsize=8)
    ax.grid(True, color=_GRID, linewidth=0.6, alpha=0.5)
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


# ── Data parsing ──────────────────────────────────────────────────────────────
def _parse_table(text: str, has_header: bool = True):
    """Parse pasted CSV / whitespace data into ordered columns.

    Returns (headers, columns) where columns maps name -> {"numeric": bool,
    "values": list}. A column is numeric only if every non-empty cell parses
    as a float.
    """
    import numpy as np

    lines = [ln for ln in text.replace("\r", "").split("\n") if ln.strip()]
    if not lines:
        raise ValueError("No data provided.")

    # delimiter sniff: comma > tab > any whitespace
    sample = lines[0]
    if "," in sample:
        split = lambda s: [c.strip() for c in s.split(",")]
    elif "\t" in sample:
        split = lambda s: [c.strip() for c in s.split("\t")]
    else:
        split = lambda s: s.split()

    rows = [split(ln) for ln in lines]
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]

    if has_header:
        headers = [h or f"col{i+1}" for i, h in enumerate(rows[0])]
        body = rows[1:]
    else:
        headers = [f"col{i+1}" for i in range(width)]
        body = rows

    if not body:
        raise ValueError("No data rows found (only a header?).")

    columns = {}
    for i, name in enumerate(headers):
        raw = [r[i] for r in body]
        cells = [c for c in raw if c != ""]
        is_num = len(cells) > 0
        for c in cells:
            try:
                float(c)
            except ValueError:
                is_num = False
                break
        if is_num:
            columns[name] = {"numeric": True,
                             "values": np.array([float(c) for c in cells], dtype="float64")}
        else:
            columns[name] = {"numeric": False, "values": [c for c in raw]}
    return headers, columns


def _numeric(columns, name):
    import numpy as np
    col = columns.get(name)
    if col is None:
        raise ValueError(f"Column '{name}' not found.")
    if not col["numeric"]:
        raise ValueError(f"Column '{name}' is not numeric.")
    return np.asarray(col["values"], dtype="float64")


# ── Describe ──────────────────────────────────────────────────────────────────
class DescribeRequest(BaseModel):
    data: str
    has_header: bool = True


@router.post("/describe")
async def describe(req: DescribeRequest):
    return await asyncio.to_thread(_describe_impl, req)


def _describe_impl(req: DescribeRequest) -> Dict[str, Any]:
    try:
        import numpy as np
        from scipy import stats as st

        headers, columns = _parse_table(req.data, req.has_header)
        out_cols = []
        for name in headers:
            col = columns[name]
            if col["numeric"]:
                v = col["values"]
                out_cols.append({
                    "name": name, "type": "numeric", "count": int(v.size),
                    "mean": float(np.mean(v)), "std": float(np.std(v, ddof=1)) if v.size > 1 else 0.0,
                    "min": float(np.min(v)), "q25": float(np.percentile(v, 25)),
                    "median": float(np.median(v)), "q75": float(np.percentile(v, 75)),
                    "max": float(np.max(v)),
                    "skew": float(st.skew(v)) if v.size > 2 else 0.0,
                    "kurtosis": float(st.kurtosis(v)) if v.size > 3 else 0.0,
                })
            else:
                vals = [x for x in col["values"] if x != ""]
                uniq = sorted(set(vals))
                out_cols.append({
                    "name": name, "type": "categorical", "count": len(vals),
                    "unique": len(uniq),
                    "top": max(uniq, key=vals.count) if vals else None,
                })
        numeric_names = [c["name"] for c in out_cols if c["type"] == "numeric"]
        return {"ok": True, "columns": out_cols, "numeric_columns": numeric_names,
                "n_rows": int(max((c["count"] for c in out_cols), default=0))}
    except Exception as exc:
        logger.warning("describe failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── Histogram + normality ─────────────────────────────────────────────────────
class HistogramRequest(BaseModel):
    data: str
    column: str
    bins: int = 30
    has_header: bool = True
    normal_fit: bool = True


@router.post("/histogram")
async def histogram(req: HistogramRequest):
    return await asyncio.to_thread(_histogram_impl, req)


def _histogram_impl(req: HistogramRequest) -> Dict[str, Any]:
    try:
        import numpy as np
        from scipy import stats as st
        plt = _plt()

        _, columns = _parse_table(req.data, req.has_header)
        v = _numeric(columns, req.column)

        fig, ax = plt.subplots(figsize=(7, 4.2))
        _style_axes(fig, ax)
        ax.hist(v, bins=max(5, min(req.bins, 200)), color=_ACCENT, alpha=0.75,
                density=req.normal_fit, edgecolor=_BG)

        normality = None
        if req.normal_fit and v.size > 2:
            mu, sigma = float(np.mean(v)), float(np.std(v, ddof=1))
            if sigma > 0:
                xs = np.linspace(v.min(), v.max(), 200)
                ax.plot(xs, st.norm.pdf(xs, mu, sigma), color=_ACCENT2,
                        linewidth=2, label=f"Normal(μ={mu:.3g}, σ={sigma:.3g})")
                ax.legend(facecolor=_BG, edgecolor=_GRID, labelcolor=_FG, fontsize=8)
            if 3 <= v.size <= 5000:
                W, p = st.shapiro(v)
                normality = {"test": "Shapiro-Wilk", "statistic": float(W),
                             "pvalue": float(p),
                             "normal": bool(p > 0.05)}

        ax.set_xlabel(req.column)
        ax.set_ylabel("density" if req.normal_fit else "count")
        ax.set_title(f"Distribution of {req.column}")
        return {"ok": True, "image": _fig_to_b64(fig), "normality": normality}
    except Exception as exc:
        logger.warning("histogram failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── Hypothesis tests ──────────────────────────────────────────────────────────
class TestRequest(BaseModel):
    data: str
    test: str                        # ttest_1samp|ttest_ind|ttest_paired|mannwhitney|anova|pearson|spearman|chisquare|normality
    columns: List[str]
    popmean: float = 0.0             # for one-sample t
    has_header: bool = True
    alpha: float = 0.05


def _verdict(p, alpha):
    return ("Reject H₀ — statistically significant"
            if p < alpha else "Fail to reject H₀ — not significant")


def _cohen_d(a, b):
    import numpy as np
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return None
    sp = math.sqrt(((na - 1) * np.var(a, ddof=1) + (nb - 1) * np.var(b, ddof=1)) / (na + nb - 2))
    if sp == 0:
        return None
    return float((np.mean(a) - np.mean(b)) / sp)


@router.post("/test")
async def test(req: TestRequest):
    return await asyncio.to_thread(_test_impl, req)


def _test_impl(req: TestRequest) -> Dict[str, Any]:
    try:
        import numpy as np
        from scipy import stats as st

        _, columns = _parse_table(req.data, req.has_header)
        t = req.test
        res: Dict[str, Any] = {"ok": True, "test": t, "alpha": req.alpha}

        if t == "ttest_1samp":
            a = _numeric(columns, req.columns[0])
            stat, p = st.ttest_1samp(a, req.popmean)
            res.update(name="One-sample t-test", statistic=float(stat), pvalue=float(p),
                       detail=f"mean={np.mean(a):.4g} vs μ₀={req.popmean}")
        elif t in ("ttest_ind", "ttest_paired"):
            a = _numeric(columns, req.columns[0]); b = _numeric(columns, req.columns[1])
            if t == "ttest_ind":
                stat, p = st.ttest_ind(a, b, equal_var=False)
                name = "Welch's two-sample t-test"
            else:
                n = min(len(a), len(b)); stat, p = st.ttest_rel(a[:n], b[:n])
                name = "Paired t-test"
            res.update(name=name, statistic=float(stat), pvalue=float(p),
                       effect={"name": "Cohen's d", "value": _cohen_d(a, b)},
                       detail=f"{req.columns[0]} μ={np.mean(a):.4g}, {req.columns[1]} μ={np.mean(b):.4g}")
        elif t == "mannwhitney":
            a = _numeric(columns, req.columns[0]); b = _numeric(columns, req.columns[1])
            stat, p = st.mannwhitneyu(a, b, alternative="two-sided")
            res.update(name="Mann–Whitney U", statistic=float(stat), pvalue=float(p),
                       detail=f"medians {np.median(a):.4g} vs {np.median(b):.4g}")
        elif t == "anova":
            groups = [_numeric(columns, c) for c in req.columns]
            stat, p = st.f_oneway(*groups)
            # eta squared
            allv = np.concatenate(groups); grand = np.mean(allv)
            ss_between = sum(len(g) * (np.mean(g) - grand) ** 2 for g in groups)
            ss_total = np.sum((allv - grand) ** 2)
            eta2 = float(ss_between / ss_total) if ss_total > 0 else None
            res.update(name="One-way ANOVA", statistic=float(stat), pvalue=float(p),
                       effect={"name": "η²", "value": eta2},
                       detail=f"{len(groups)} groups")
        elif t in ("pearson", "spearman"):
            a = _numeric(columns, req.columns[0]); b = _numeric(columns, req.columns[1])
            n = min(len(a), len(b)); a, b = a[:n], b[:n]
            if t == "pearson":
                r, p = st.pearsonr(a, b); name = "Pearson correlation"
            else:
                r, p = st.spearmanr(a, b); name = "Spearman correlation"
            res.update(name=name, statistic=float(r), pvalue=float(p),
                       effect={"name": "r²", "value": float(r * r)},
                       detail=f"n={n}")
        elif t == "chisquare":
            a = _numeric(columns, req.columns[0])
            stat, p = st.chisquare(a)
            res.update(name="Chi-square goodness-of-fit", statistic=float(stat),
                       pvalue=float(p), detail="vs uniform expected")
        elif t == "normality":
            a = _numeric(columns, req.columns[0])
            stat, p = st.shapiro(a)
            res.update(name="Shapiro–Wilk normality", statistic=float(stat), pvalue=float(p),
                       detail="H₀: data is normally distributed")
        else:
            return {"ok": False, "error": f"Unknown test: {t}"}

        res["verdict"] = _verdict(res["pvalue"], req.alpha)
        res["significant"] = bool(res["pvalue"] < req.alpha)
        return res
    except Exception as exc:
        logger.warning("test failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── Regression (OLS) ──────────────────────────────────────────────────────────
class RegressionRequest(BaseModel):
    data: str
    x: str
    y: str
    has_header: bool = True


@router.post("/regression")
async def regression(req: RegressionRequest):
    return await asyncio.to_thread(_regression_impl, req)


def _regression_impl(req: RegressionRequest) -> Dict[str, Any]:
    try:
        import numpy as np
        from scipy import stats as st
        plt = _plt()

        _, columns = _parse_table(req.data, req.has_header)
        x = _numeric(columns, req.x); y = _numeric(columns, req.y)
        n = min(len(x), len(y)); x, y = x[:n], y[:n]
        if n < 3:
            return {"ok": False, "error": "Need at least 3 paired points."}

        lr = st.linregress(x, y)
        xs = np.linspace(x.min(), x.max(), 100)
        ys = lr.slope * xs + lr.intercept

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.5, 4.0),
                                       gridspec_kw={"width_ratios": [1.5, 1]})
        _style_axes(fig, ax1); _style_axes(fig, ax2)
        ax1.scatter(x, y, color=_ACCENT, s=22, alpha=0.8, edgecolor=_BG)
        ax1.plot(xs, ys, color=_ACCENT2, linewidth=2,
                 label=f"y = {lr.slope:.4g}x + {lr.intercept:.4g}")
        ax1.set_xlabel(req.x); ax1.set_ylabel(req.y); ax1.set_title("Fit")
        ax1.legend(facecolor=_BG, edgecolor=_GRID, labelcolor=_FG, fontsize=8)

        resid = y - (lr.slope * x + lr.intercept)
        ax2.scatter(lr.slope * x + lr.intercept, resid, color=_SERIES[2], s=18, alpha=0.8, edgecolor=_BG)
        ax2.axhline(0, color=_GRID, linewidth=1)
        ax2.set_xlabel("fitted"); ax2.set_ylabel("residual"); ax2.set_title("Residuals")

        return {
            "ok": True, "image": _fig_to_b64(fig),
            "slope": float(lr.slope), "intercept": float(lr.intercept),
            "r": float(lr.rvalue), "r2": float(lr.rvalue ** 2),
            "pvalue": float(lr.pvalue), "stderr": float(lr.stderr), "n": int(n),
        }
    except Exception as exc:
        logger.warning("regression failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── Explore: PCA + KMeans ─────────────────────────────────────────────────────
class ExploreRequest(BaseModel):
    data: str
    columns: List[str]
    clusters: int = 3
    has_header: bool = True


@router.post("/explore")
async def explore(req: ExploreRequest):
    return await asyncio.to_thread(_explore_impl, req)


def _explore_impl(req: ExploreRequest) -> Dict[str, Any]:
    try:
        import numpy as np
        from sklearn.decomposition import PCA
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
        plt = _plt()

        _, columns = _parse_table(req.data, req.has_header)
        cols = [c for c in req.columns if columns.get(c, {}).get("numeric")]
        if len(cols) < 2:
            return {"ok": False, "error": "Select at least 2 numeric columns."}

        mats = [_numeric(columns, c) for c in cols]
        n = min(len(m) for m in mats)
        X = np.column_stack([m[:n] for m in mats])
        if n < 3:
            return {"ok": False, "error": "Need at least 3 rows."}

        Xs = StandardScaler().fit_transform(X)
        k = max(2, min(req.clusters, n - 1, 8))
        labels = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(Xs)

        pca = PCA(n_components=2)
        pcs = pca.fit_transform(Xs)

        fig, ax = plt.subplots(figsize=(6.4, 4.6))
        _style_axes(fig, ax)
        for c in range(k):
            m = labels == c
            ax.scatter(pcs[m, 0], pcs[m, 1], s=26, alpha=0.85,
                       color=_SERIES[c % len(_SERIES)], edgecolor=_BG, label=f"cluster {c}")
        ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]*100:.0f}%)")
        ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]*100:.0f}%)")
        ax.set_title(f"PCA · KMeans (k={k})")
        ax.legend(facecolor=_BG, edgecolor=_GRID, labelcolor=_FG, fontsize=8)

        return {
            "ok": True, "image": _fig_to_b64(fig), "k": int(k),
            "explained_variance": [float(v) for v in pca.explained_variance_ratio_[:2]],
            "cluster_sizes": [int((labels == c).sum()) for c in range(k)],
        }
    except Exception as exc:
        logger.warning("explore failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── AI layer (optional) ───────────────────────────────────────────────────────
class RecommendRequest(BaseModel):
    question: str
    columns_summary: str = ""
    model_id: str = "auto"


_RECOMMEND_SYSTEM = (
    "You are a statistics research assistant. Given a research question and a "
    "short description of the available columns, recommend the single most "
    "appropriate analysis the user can run in this tool (descriptive summary, "
    "histogram + Shapiro normality, one/two-sample or paired t-test, Mann–Whitney "
    "U, one-way ANOVA, Pearson/Spearman correlation, chi-square, linear "
    "regression, or PCA + KMeans). State which columns to use, the assumptions to "
    "check first, and why. Do not invent numbers — the engine computes them."
)

_INTERPRET_SYSTEM = (
    "You are a statistics research assistant. You are given a test/analysis result "
    "computed by the engine. Explain what it means for the research question, "
    "state whether it is significant and how large the effect is, and flag "
    "assumption caveats. The numbers are correct — interpret, do not recompute."
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
                    prompt=full_prompt, trace_id=trace_id, temperature=0.3,
                    model=model_id, request_type="generation", source=CallSource.RESEARCH,
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
            logger.error("stats-lab LLM error: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/recommend")
async def recommend(req: RecommendRequest):
    prompt = f"Question: {req.question}\nColumns: {req.columns_summary}"
    return _stream_llm(prompt, _RECOMMEND_SYSTEM, req.model_id, "stats-recommend")


class InterpretRequest(BaseModel):
    context: str
    model_id: str = "auto"


@router.post("/interpret")
async def interpret(req: InterpretRequest):
    return _stream_llm(req.context, _INTERPRET_SYSTEM, req.model_id, "stats-interpret")


# alias for server.py registration
stats_router = router
