"""
core/interfaces/dashboard/trellis_patches.py
Source patches applied to a cloned microsoft/TRELLIS checkout so it runs without
xformers / flash_attn, using PyTorch's built-in scaled_dot_product_attention ("sdpa").

Used by the 3D installer and by the worker launcher (which re-applies them when it
finds an install made by the old, broken patcher).  The functions are idempotent:
each file is restored from git first, then patched with exact, anchored edits, and
compiled to make sure the result is valid Python.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ATTN_DIR = Path("trellis") / "modules" / "sparse" / "attention"
_FILES = ("full_attn.py", "serialized_attn.py", "windowed_attn.py")
_MARKER = "# [aethvion] sdpa backend"

_IMPORT_OLD = (
    "elif ATTN == 'flash_attn':\n"
    "    import flash_attn\n"
    "else:\n"
    "    raise ValueError(f\"Unknown attention module: {ATTN}\")\n"
)
_IMPORT_NEW = (
    "elif ATTN == 'flash_attn':\n"
    "    import flash_attn\n"
    "elif ATTN == 'sdpa':\n"
    f"    pass  {_MARKER}\n"
    "else:\n"
    "    raise ValueError(f\"Unknown attention module: {ATTN}\")\n"
)

# full_attn.py — q [T_Q, H, C], k / v [T_KV, H, C]; one attention call per batch item
_FULL_OLD = (
    "    else:\n"
    "        raise ValueError(f\"Unknown attention module: {ATTN}\")\n"
    "    \n"
    "    if s is not None:\n"
)
_FULL_NEW = (
    "    elif ATTN == 'sdpa':\n"
    "        if num_all_args == 1:\n"
    "            q, k, v = qkv.unbind(dim=1)\n"
    "        elif num_all_args == 2:\n"
    "            k, v = kv.unbind(dim=1)\n"
    "        out_list = []\n"
    "        q_start, kv_start = 0, 0\n"
    "        for i in range(len(q_seqlen)):\n"
    "            qi = q[q_start:q_start + q_seqlen[i]].transpose(0, 1).unsqueeze(0)      # [1, H, Lq, C]\n"
    "            ki = k[kv_start:kv_start + kv_seqlen[i]].transpose(0, 1).unsqueeze(0)   # [1, H, Lkv, C]\n"
    "            vi = v[kv_start:kv_start + kv_seqlen[i]].transpose(0, 1).unsqueeze(0)\n"
    "            res = torch.nn.functional.scaled_dot_product_attention(qi, ki, vi)\n"
    "            out_list.append(res.squeeze(0).transpose(0, 1))                         # [Lq, H, C]\n"
    "            q_start += q_seqlen[i]\n"
    "            kv_start += kv_seqlen[i]\n"
    "        out = torch.cat(out_list, dim=0)\n"
) + _FULL_OLD

# serialized_attn.py / windowed_attn.py — equal-length windows: one batched call
_DENSE_OLD = (
    "            out = flash_attn.flash_attn_qkvpacked_func(qkv_feats)   # [B, N, H, C]\n"
    "        else:\n"
)
_DENSE_NEW = (
    "            out = flash_attn.flash_attn_qkvpacked_func(qkv_feats)   # [B, N, H, C]\n"
    "        elif ATTN == 'sdpa':\n"
    "            q, k, v = qkv_feats.unbind(dim=2)                       # [B, N, H, C]\n"
    "            out = torch.nn.functional.scaled_dot_product_attention(\n"
    "                q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2))   # [B, H, N, C]\n"
    "            out = out.transpose(1, 2)                               # [B, N, H, C]\n"
    "        else:\n"
)

# …and variable-length windows: one call per window
_VARLEN_OLD = (
    "            out = flash_attn.flash_attn_varlen_qkvpacked_func(qkv_feats, cu_seqlens, max(seq_lens)) # [M, H, C]\n"
)
_VARLEN_NEW = _VARLEN_OLD + (
    "        elif ATTN == 'sdpa':\n"
    "            q, k, v = qkv_feats.unbind(dim=1)                       # [M, H, C]\n"
    "            out_list = []\n"
    "            curr = 0\n"
    "            for slen in seq_lens:\n"
    "                qi = q[curr:curr + slen].transpose(0, 1).unsqueeze(0)   # [1, H, L, C]\n"
    "                ki = k[curr:curr + slen].transpose(0, 1).unsqueeze(0)\n"
    "                vi = v[curr:curr + slen].transpose(0, 1).unsqueeze(0)\n"
    "                res = torch.nn.functional.scaled_dot_product_attention(qi, ki, vi)\n"
    "                out_list.append(res.squeeze(0).transpose(0, 1))\n"
    "                curr += slen\n"
    "            out = torch.cat(out_list, dim=0)\n"
    "        else:\n"
    "            raise ValueError(f\"Unknown attention module: {ATTN}\")\n"
)


def _replace_once(text: str, old: str, new: str, what: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"expected exactly one '{what}' block, found {text.count(old)} "
                           "(the TRELLIS source changed — the patch needs updating)")
    return text.replace(old, new)


def is_patched(repo_dir: Path) -> bool:
    """True when every attention file carries a valid sdpa patch."""
    for name in _FILES:
        f = repo_dir / _ATTN_DIR / name
        try:
            src = f.read_text(encoding="utf-8")
            if _MARKER not in src:
                return False
            compile(src, str(f), "exec")
        except (OSError, SyntaxError):
            return False
    return True


def apply_sdpa_patches(repo_dir: Path) -> list[str]:
    """Patch the sparse attention modules for the sdpa backend.  Returns log lines.

    Raises RuntimeError if a file cannot be patched cleanly; in that case the file is
    left as the unmodified upstream version rather than half-patched.
    """
    repo_dir = Path(repo_dir)
    log: list[str] = []

    init_file = repo_dir / "trellis" / "modules" / "sparse" / "__init__.py"
    if init_file.exists():
        c = init_file.read_text(encoding="utf-8")
        if "'flash_attn', 'sdpa']" not in c:
            c = c.replace("['xformers', 'flash_attn']", "['xformers', 'flash_attn', 'sdpa']")
            init_file.write_text(c, encoding="utf-8", newline="\n")
            log.append("sparse/__init__.py: 'sdpa' accepted as attention backend")

    for name in _FILES:
        rel = (_ATTN_DIR / name).as_posix()
        f = repo_dir / _ATTN_DIR / name
        # Start from the pristine upstream file every time (undoes any earlier bad patch).
        res = subprocess.run(["git", "checkout", "--", rel], cwd=str(repo_dir), capture_output=True, text=True,
                             creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        if res.returncode != 0:
            raise RuntimeError(f"could not restore {rel} from git: {res.stderr.strip()}")
        original = f.read_text(encoding="utf-8").replace("\r\n", "\n")

        src = _replace_once(original, _IMPORT_OLD, _IMPORT_NEW, "attention import")
        if name == "full_attn.py":
            src = _replace_once(src, _FULL_OLD, _FULL_NEW, "full attention dispatch")
        else:
            src = _replace_once(src, _DENSE_OLD, _DENSE_NEW, "fixed-window dispatch")
            src = _replace_once(src, _VARLEN_OLD, _VARLEN_NEW, "variable-window dispatch")

        compile(src, str(f), "exec")   # never write a file that does not parse
        f.write_text(src, encoding="utf-8", newline="\n")
        log.append(f"{name}: sdpa backend added")
    return log
