"""
Aethvion Suite - Chemistry & Biology Lab Routes

Real cheminformatics and bioinformatics. Molecular properties, structures and
fingerprint similarity come from RDKit; sequence analysis, translation and
alignment from Biopython. The AI layer only interprets a computed result; it
never invents chemistry or biology.

API prefix: /api/chembio
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

logger = get_logger("web.chembio_routes")
router = APIRouter(prefix="/api/chembio", tags=["ChemBio"])


# ── Chemistry (RDKit) ─────────────────────────────────────────────────────────
def _mol_image(mol, size=(320, 240)) -> Optional[str]:
    """Render a molecule to a base64 PNG on a dark, dashboard-matched canvas."""
    try:
        from rdkit.Chem.Draw import rdMolDraw2D
        from rdkit.Chem import AllChem
        AllChem.Compute2DCoords(mol)
        drawer = rdMolDraw2D.MolDraw2DCairo(size[0], size[1])
        opts = drawer.drawOptions()
        opts.clearBackground = False
        # light atoms on the dark UI
        opts.setBackgroundColour((0.05, 0.055, 0.086, 1.0))
        opts.legendColour = (0.96, 0.96, 0.98)
        drawer.DrawMolecule(mol)
        drawer.FinishDrawing()
        png = drawer.GetDrawingText()
        return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    except Exception as exc:
        logger.debug("mol image render failed (%s); trying PIL fallback", exc)
        try:
            from rdkit.Chem import Draw
            img = Draw.MolToImage(mol, size=size)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            return None


class MoleculeRequest(BaseModel):
    smiles: str


@router.post("/molecule")
async def molecule(req: MoleculeRequest):
    return await asyncio.to_thread(_molecule_impl, req)


def _molecule_impl(req: MoleculeRequest) -> Dict[str, Any]:
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, rdMolDescriptors, Lipinski

        smi = req.smiles.strip()
        if not smi:
            return {"ok": False, "error": "Enter a SMILES string."}
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            return {"ok": False, "error": f"Could not parse SMILES: {smi}"}

        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        hbd = Lipinski.NumHDonors(mol)
        hba = Lipinski.NumHAcceptors(mol)

        # Lipinski rule-of-five
        violations = sum([mw > 500, logp > 5, hbd > 5, hba > 10])

        props = {
            "formula": rdMolDescriptors.CalcMolFormula(mol),
            "mol_weight": round(mw, 2),
            "logp": round(logp, 2),
            "tpsa": round(Descriptors.TPSA(mol), 2),
            "h_donors": int(hbd),
            "h_acceptors": int(hba),
            "rotatable_bonds": int(Descriptors.NumRotatableBonds(mol)),
            "rings": int(rdMolDescriptors.CalcNumRings(mol)),
            "aromatic_rings": int(rdMolDescriptors.CalcNumAromaticRings(mol)),
            "heavy_atoms": int(mol.GetNumHeavyAtoms()),
            "fraction_csp3": round(Descriptors.FractionCSP3(mol), 3),
        }
        return {
            "ok": True,
            "canonical_smiles": Chem.MolToSmiles(mol),
            "properties": props,
            "lipinski": {"violations": int(violations), "passes": bool(violations <= 1)},
            "image": _mol_image(mol),
        }
    except ImportError:
        return {"ok": False, "error": "RDKit is not installed. Restart the app to auto-install, or `pip install rdkit`."}
    except Exception as exc:
        logger.warning("molecule failed: %s", exc)
        return {"ok": False, "error": str(exc)}


class SimilarityRequest(BaseModel):
    smiles_a: str
    smiles_b: str


@router.post("/similarity")
async def similarity(req: SimilarityRequest):
    return await asyncio.to_thread(_similarity_impl, req)


def _similarity_impl(req: SimilarityRequest) -> Dict[str, Any]:
    try:
        from rdkit import Chem, DataStructs
        from rdkit.Chem import rdFingerprintGenerator

        a = Chem.MolFromSmiles(req.smiles_a.strip())
        b = Chem.MolFromSmiles(req.smiles_b.strip())
        if a is None or b is None:
            bad = req.smiles_a if a is None else req.smiles_b
            return {"ok": False, "error": f"Could not parse SMILES: {bad}"}

        gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
        fp_a, fp_b = gen.GetFingerprint(a), gen.GetFingerprint(b)
        tanimoto = DataStructs.TanimotoSimilarity(fp_a, fp_b)
        dice = DataStructs.DiceSimilarity(fp_a, fp_b)

        return {
            "ok": True,
            "tanimoto": round(tanimoto, 4),
            "dice": round(dice, 4),
            "image_a": _mol_image(a),
            "image_b": _mol_image(b),
        }
    except ImportError:
        return {"ok": False, "error": "RDKit is not installed."}
    except Exception as exc:
        logger.warning("similarity failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── Biology (Biopython) ───────────────────────────────────────────────────────
def _detect_seq_type(seq: str) -> str:
    s = set(seq.upper()) - {"N", "-", "*"}
    if s <= set("ACGT"):
        return "dna"
    if s <= set("ACGU"):
        return "rna"
    return "protein"


class SequenceRequest(BaseModel):
    sequence: str
    seq_type: str = "auto"   # auto|dna|rna|protein


@router.post("/sequence")
async def sequence(req: SequenceRequest):
    return await asyncio.to_thread(_sequence_impl, req)


def _sequence_impl(req: SequenceRequest) -> Dict[str, Any]:
    try:
        from Bio.Seq import Seq
        from Bio.SeqUtils import gc_fraction

        raw = "".join(req.sequence.split()).upper()
        if not raw:
            return {"ok": False, "error": "Enter a sequence."}
        stype = req.seq_type if req.seq_type != "auto" else _detect_seq_type(raw)

        out: Dict[str, Any] = {"ok": True, "seq_type": stype, "length": len(raw)}

        if stype in ("dna", "rna"):
            seq = Seq(raw)
            out["gc_percent"] = round(gc_fraction(seq) * 100, 2)
            comp = {b: raw.count(b) for b in ("ACGU" if stype == "rna" else "ACGT")}
            out["composition"] = comp
            try:
                out["complement"] = str(seq.complement())
                out["reverse_complement"] = str(seq.reverse_complement())
            except Exception:
                pass
            if stype == "dna":
                out["transcribed_rna"] = str(seq.transcribe())
            # translation (trim to codon multiple)
            trim = raw[: len(raw) - (len(raw) % 3)]
            if trim:
                protein = str(Seq(trim).translate())
                out["protein"] = protein
                out["stop_codons"] = protein.count("*")
        else:
            from Bio.SeqUtils.ProtParam import ProteinAnalysis
            clean = raw.replace("*", "").replace("-", "")
            valid = set("ACDEFGHIKLMNPQRSTVWY")
            if not set(clean) <= valid:
                bad = "".join(sorted(set(clean) - valid))
                return {"ok": False, "error": f"Invalid amino-acid letters: {bad}"}
            pa = ProteinAnalysis(clean)
            out["mol_weight"] = round(pa.molecular_weight(), 1)
            out["isoelectric_point"] = round(pa.isoelectric_point(), 2)
            out["aromaticity"] = round(pa.aromaticity(), 3)
            out["instability_index"] = round(pa.instability_index(), 2)
            out["gravy"] = round(pa.gravy(), 3)
            # Biopython 1.87's amino_acids_percent already returns percentages (0–100).
            pct = pa.amino_acids_percent
            out["composition"] = {k: round(v, 1) for k, v in pct.items() if v > 0}
        return out
    except ImportError:
        return {"ok": False, "error": "Biopython is not installed. Restart to auto-install, or `pip install biopython`."}
    except Exception as exc:
        logger.warning("sequence failed: %s", exc)
        return {"ok": False, "error": str(exc)}


class AlignRequest(BaseModel):
    seq_a: str
    seq_b: str
    mode: str = "global"   # global|local


@router.post("/align")
async def align(req: AlignRequest):
    return await asyncio.to_thread(_align_impl, req)


def _align_impl(req: AlignRequest) -> Dict[str, Any]:
    try:
        from Bio.Align import PairwiseAligner

        a = "".join(req.seq_a.split()).upper()
        b = "".join(req.seq_b.split()).upper()
        if not a or not b:
            return {"ok": False, "error": "Enter both sequences."}

        aligner = PairwiseAligner()
        aligner.mode = "local" if req.mode == "local" else "global"
        aligner.match_score = 2
        aligner.mismatch_score = -1
        aligner.open_gap_score = -2
        aligner.extend_gap_score = -0.5

        alignments = aligner.align(a, b)
        best = alignments[0]
        text = str(best)

        # identity from the aligned block characters
        lines = text.split("\n")
        matches = sum(l.count("|") for l in lines)
        aligned_len = max(len(a), len(b))
        identity = round(100.0 * matches / aligned_len, 1) if aligned_len else 0.0

        # cap the rendered alignment so huge sequences don't flood the UI
        if len(text) > 6000:
            text = text[:6000] + "\n… (truncated)"

        return {
            "ok": True,
            "mode": aligner.mode,
            "score": float(best.score),
            "identity_percent": identity,
            "alignment": text,
        }
    except ImportError:
        return {"ok": False, "error": "Biopython is not installed."}
    except Exception as exc:
        logger.warning("align failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── AI layer (optional) ───────────────────────────────────────────────────────
class InterpretRequest(BaseModel):
    context: str
    model_id: str = "auto"


_INTERPRET_SYSTEM = (
    "You are a chemistry and molecular-biology research assistant. You are given "
    "a computed result (molecular properties, fingerprint similarity, a sequence "
    "analysis, or an alignment). Explain what it means: drug-likeness and what the "
    "properties imply, what a similarity score suggests, what a sequence's "
    "composition/translation indicates, or how significant an alignment is. Be "
    "rigorous and concise. The values are correct — interpret, do not recompute."
)


@router.post("/interpret")
async def interpret(req: InterpretRequest):
    async def event_generator():
        try:
            from core.providers.provider_manager import get_provider_manager
            from core.ai.call_contexts import CallSource

            pm = get_provider_manager()
            trace_id = f"chembio-interpret-{uuid.uuid4().hex[:8]}"
            full_prompt = f"{_INTERPRET_SYSTEM}\n\n=== RESULT ===\n{req.context}\n\nInterpretation:"

            def _call():
                return pm.call_with_failover(
                    prompt=full_prompt, trace_id=trace_id, temperature=0.3,
                    model=req.model_id, request_type="generation", source=CallSource.RESEARCH,
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
            logger.error("chembio LLM error: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# alias for server.py registration
chembio_router = router
