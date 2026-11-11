"""
Tests for the Model Hub, Asset Library and the workflow-engine upgrades
(branch pruning, cancel, sub-workflows, for-each, retry-until).

Everything runs offline: models are the built-in demo endpoints, a throw-away local
HTTP server, and a Python one-liner used as a "command-line tool".
"""
from __future__ import annotations

import base64
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from core.assets import store, values
from core.automate.executor import WorkflowExecutor
from core.modelhub import glb, hub, registry
from core.modelhub.templating import LazyVars, lookup, render


# Fixtures

@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Point the asset store, custom endpoints and saved workflows at a temp folder."""
    monkeypatch.setattr(store, "ASSETS_ROOT", tmp_path / "assets")
    monkeypatch.setattr(store, "_FILES_DIR", tmp_path / "assets" / "files")
    monkeypatch.setattr(store, "_META_DIR", tmp_path / "assets" / "meta")
    monkeypatch.setattr(store, "_cache", None)
    monkeypatch.setattr(registry, "ENDPOINTS_DIR", tmp_path / "endpoints")
    import core.automate.automate_routes as routes
    monkeypatch.setattr(routes, "_DATA_DIR", tmp_path / "workflows")
    (tmp_path / "workflows").mkdir()
    yield tmp_path


def _wf(nodes, conns, name="test", wf_id="wf_test"):
    return {"id": wf_id, "name": name, "nodes": nodes, "connections": conns}


def _n(nid, ntype, **props):
    return {"id": nid, "type": ntype, "label": nid, "properties": props}


def _c(src, sport, tgt, tport):
    return {"sourceNodeId": src, "sourcePort": sport, "targetNodeId": tgt, "targetPort": tport}


def _trig(tgt):
    return _c("t", "trigger", tgt, "__trigger__")


def _save_wf(tmp_path, wf):
    (tmp_path / "workflows" / f"{wf['id']}.json").write_text(json.dumps(wf), encoding="utf-8")


# Templating

def test_template_rendering_and_lookup():
    v = LazyVars({"prompt": "a sword", "params": {"seed": 7}, "big": lambda: "LAZY",
                  "response": {"data": [{"url": "http://x/y.glb"}]}})
    assert render("{{params.seed}}", v) == 7                      # type preserved
    assert render("seed-{{params.seed}}", v) == "seed-7"
    assert render({"a": "{{prompt}}", "b": "{{missing}}"}, v) == {"a": "a sword"}   # optional dropped
    assert render("{{big}}", v) == "LAZY"
    assert lookup(v, "response.data[0].url") == "http://x/y.glb"
    assert lookup(v, "response.data[3].url") is None


# GLB helpers

def test_glb_roundtrip_and_inspect(tmp_path):
    box = glb.make_box_glb((2, 1, 1))
    p = tmp_path / "box.glb"
    p.write_bytes(box)
    stats = glb.inspect_mesh(p)
    assert stats["triangles"] == 12 and stats["vertices"] == 24
    assert stats["has_uvs"] and stats["has_normals"] and not stats["is_textured"]
    assert stats["size"] == [2.0, 1.0, 1.0]

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    textured = glb.apply_base_color_texture(box, png)
    p2 = tmp_path / "tex.glb"
    p2.write_bytes(textured)
    stats2 = glb.inspect_mesh(p2)
    assert stats2["is_textured"] and stats2["textures"] == 1 and stats2["triangles"] == 12
    images = glb.extract_images(p2)
    assert len(images) == 1 and images[0][2] == png


# Asset store

def test_asset_store_lineage_and_values():
    a = store.create_from_bytes(b"concept", ext="png", name="concept")
    b = store.create_from_bytes(b"mesh", ext="glb", name="mesh", parents=[a["id"]], tags=["prop"])
    c = store.create_from_bytes(b"textured", ext="glb", parents=[b["id"]])
    assert a["kind"] == "image" and b["kind"] == "mesh"
    lin = store.lineage(b["id"])
    assert [r["id"] for r in lin["ancestors"]] == [a["id"]]
    assert [r["id"] for r in lin["descendants"]] == [c["id"]]
    assert store.list_assets(kind="mesh")["total"] == 2
    assert store.list_assets(tag="prop")["total"] == 1

    ref = store.asset_ref(b)
    assert values.as_asset_ref(json.dumps(ref))["id"] == b["id"]      # survives a text-only hop
    assert values.as_asset_ref(b["id"])["id"] == b["id"]
    assert values.read_media(ref)[0] == b"mesh"
    assert values.read_media("data:image/png;base64," + base64.b64encode(b"x").decode())[0] == b"x"
    assert store.delete(c["id"]) and store.get(c["id"]) is None


# Model Hub

def test_demo_pipeline_generates_textured_mesh_with_lineage():
    mesh = hub.invoke("demo:mesh", "mesh.generate", prompt="a wooden crate")
    assert mesh.ok and mesh.assets[0]["kind"] == "mesh"
    tex = hub.invoke("demo:texture", "mesh.texture", prompt="weathered oak", mesh=mesh.refs[0])
    assert tex.ok
    assert tex.assets[0]["parents"] == [mesh.assets[0]["id"]]
    assert glb.inspect_mesh(tex.assets[0]["path"])["is_textured"]


def test_hub_reports_problems_without_raising():
    assert "does not support" in hub.invoke("demo:mesh", "image.generate").error
    assert "Unknown model endpoint" in hub.invoke("nope", "mesh.generate").error
    assert "No model endpoint" in hub.invoke("", "mesh.generate").error


class _FakeModelServer(BaseHTTPRequestHandler):
    """Mimics an async 3D API: POST /jobs -> id, GET /jobs/<id> -> status, then a file URL."""
    polls = 0
    last_body: dict = {}

    def log_message(self, *args):  # silence
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        type(self).last_body = body
        if self.path == "/sync":
            self._json({"success": True, "glb_base64": base64.b64encode(glb.make_box_glb()).decode()})
        elif self.path == "/jobs":
            self._json({"result": "job42"})
        else:
            self._json({"error": "nope"}, 404)

    def do_GET(self):
        if self.path == "/jobs/job42":
            type(self).polls += 1
            if type(self).polls < 2:
                self._json({"status": "IN_PROGRESS", "progress": 50})
            else:
                host = self.headers.get("Host")
                self._json({"status": "SUCCEEDED", "model_urls": {"glb": f"http://{host}/files/out.glb"}})
        elif self.path == "/files/out.glb":
            data = glb.make_box_glb()
            self.send_response(200)
            self.send_header("Content-Type", "model/gltf-binary")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self._json({"error": "nope"}, 404)


@pytest.fixture
def model_server():
    _FakeModelServer.polls = 0
    srv = HTTPServer(("127.0.0.1", 0), _FakeModelServer)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_custom_http_endpoint_sync_base64(model_server):
    registry.save_custom({
        "id": "my-3d-server", "name": "My 3D server", "capabilities": ["mesh.generate"], "adapter": "http",
        "http": {"url": f"{model_server}/sync",
                 "body": {"prompt": "{{prompt}}", "image_base64": "{{image_b64}}", "seed": "{{params.seed}}"},
                 "result": {"type": "base64", "path": "glb_base64", "success_path": "success"}},
        "params": [{"key": "seed", "type": "number", "default": 5}],
        "output": {"kind": "mesh", "ext": "glb"},
    })
    assert any(e["id"] == "my-3d-server" for e in registry.list_endpoints("mesh.generate"))
    r = hub.invoke("my-3d-server", "mesh.generate", prompt="a barrel")
    assert r.ok, r.error
    assert r.assets[0]["kind"] == "mesh" and r.assets[0]["ext"] == "glb"
    # optional image input was dropped from the body; param default applied with its type
    assert _FakeModelServer.last_body == {"prompt": "a barrel", "seed": 5}


def test_custom_http_endpoint_async_polling_and_download(model_server):
    registry.save_custom({
        "id": "hosted-3d", "name": "Hosted 3D", "capabilities": ["mesh.generate"], "adapter": "http",
        "http": {"url": f"{model_server}/jobs", "body": {"prompt": "{{prompt}}"},
                 "poll": {"url": f"{model_server}/jobs/{{{{response.result}}}}", "status_path": "status",
                          "done": ["SUCCEEDED"], "failed": ["FAILED"], "interval": 0.5, "timeout": 20},
                 "result": {"type": "url", "path": "model_urls.glb"}},
    })
    r = hub.invoke("hosted-3d", "mesh.generate", prompt="a chest")
    assert r.ok, r.error
    assert glb.inspect_mesh(r.assets[0]["path"])["triangles"] == 12


def test_custom_command_endpoint(tmp_path):
    script = tmp_path / "tool.py"
    script.write_text(
        "import sys, shutil\n"
        "shutil.copyfile(sys.argv[1], sys.argv[2])\n"
        "print('processed', sys.argv[3])\n", encoding="utf-8")
    registry.save_custom({
        "id": "copy-tool", "name": "Copy tool", "capabilities": ["mesh.process"], "adapter": "command",
        "requires": ["mesh"],
        "command": {"args": [sys.executable, str(script), "{{mesh_path}}", "{{output_path}}", "{{params.ratio}}"]},
        "params": [{"key": "ratio", "type": "number", "default": 0.5}],
        "output": {"kind": "mesh", "ext": "glb"},
    })
    src = hub.invoke("demo:mesh", "mesh.generate", prompt="x")
    r = hub.invoke("copy-tool", "mesh.process", mesh=src.refs[0])
    assert r.ok, r.error
    assert r.assets[0]["parents"] == [src.assets[0]["id"]]
    assert "processed 0.5" in r.text
    assert "requires a 'mesh' input" in hub.invoke("copy-tool", "mesh.process").error


def test_endpoint_validation():
    assert registry.validate_definition({"id": "x"})
    assert not registry.validate_definition({
        "id": "ok-one", "name": "OK", "capabilities": ["custom"], "adapter": "command", "command": {"args": ["echo"]}})
    with pytest.raises(ValueError):
        registry.save_custom({"id": "Bad Id", "name": "", "capabilities": [], "adapter": "ftp"})


# Executor: branching

def test_untaken_branch_is_skipped():
    wf = _wf(
        [_n("t", "trigger.manual"), _n("src", "input.text", value="hello"),
         _n("if", "logic.if", condition="value == 'hello'"),
         _n("yes", "data.template", template="YES {{input}}"), _n("no", "data.template", template="NO {{input}}"),
         _n("after_no", "data.template", template="after"),
         _n("merge", "logic.merge", mode="first")],
        [_trig("if"), _c("src", "out", "if", "in"),
         _c("if", "true", "yes", "in"), _c("if", "false", "no", "in"), _c("no", "out", "after_no", "in"),
         _c("yes", "out", "merge", "a"), _c("after_no", "out", "merge", "b")],
    )
    res = WorkflowExecutor(wf).execute()
    assert res["ok"]
    assert res["node_status"]["yes"] == "done"
    assert res["node_status"]["no"] == "skipped"          # branch not taken
    assert res["node_status"]["after_no"] == "skipped"    # …and everything behind it
    assert res["node_status"]["merge"] == "done"          # still has one live input
    assert res["node_outputs"]["merge"]["source"] == "a"


def test_pruning_can_be_disabled():
    wf = _wf(
        [_n("t", "trigger.manual"), _n("src", "input.text", value="hello"),
         _n("if", "logic.if", condition="value == 'nope'"), _n("yes", "data.template", template="x")],
        [_trig("if"), _c("src", "out", "if", "in"), _c("if", "true", "yes", "in")],
    )
    assert WorkflowExecutor(wf).execute()["node_status"]["yes"] == "skipped"
    wf["settings"] = {"prune_dead_branches": False}
    assert WorkflowExecutor(wf).execute()["node_status"]["yes"] == "done"


def test_downstream_of_failed_node_is_skipped():
    wf = _wf(
        [_n("t", "trigger.manual"), _n("gen", "model3d.generate", endpoint="does-not-exist", prompt="x"),
         _n("tex", "model3d.texture", endpoint="demo:texture")],
        [_trig("gen"), _c("gen", "mesh", "tex", "mesh")],
    )
    res = WorkflowExecutor(wf).execute()
    assert not res["ok"]
    assert res["node_status"]["gen"] == "error" and "Unknown model endpoint" in res["node_errors"]["gen"]
    assert res["node_status"]["tex"] == "skipped"


def test_error_port_routes_failure_instead_of_raising():
    wf = _wf(
        [_n("t", "trigger.manual"), _n("gen", "model3d.generate", endpoint="does-not-exist", prompt="x"),
         _n("tex", "model3d.texture", endpoint="demo:texture"), _n("onerr", "data.template", template="handled: {{input}}")],
        [_trig("gen"), _c("gen", "mesh", "tex", "mesh"), _c("gen", "error", "onerr", "in")],
    )
    res = WorkflowExecutor(wf).execute()
    assert res["ok"] and res["node_status"]["gen"] == "done"
    assert res["node_status"]["tex"] == "skipped" and res["node_status"]["onerr"] == "done"


def test_cancel_stops_scheduling():
    wf = _wf([_n("t", "trigger.manual"), _n("a", "data.template", template="a"), _n("b", "data.template", template="b")],
             [_trig("a"), _c("a", "out", "b", "in")])
    ex = WorkflowExecutor(wf)
    ex.cancel()
    res = ex.execute()
    assert res["cancelled"] and not res["ok"]
    assert res["node_status"]["a"] == "skipped" and res["node_status"]["b"] == "skipped"


# Executor: the 3D pipeline from the brief (generate -> texture -> verify)

def test_3d_pipeline_generate_texture_inspect_export(tmp_path):
    wf = _wf(
        [_n("t", "trigger.manual"), _n("brief", "input.text", value="a wooden crate"),
         _n("gen", "model3d.generate", endpoint="demo:mesh", tags="crate, test"),
         _n("tex", "model3d.texture", endpoint="demo:texture", prompt="weathered oak"),
         _n("check", "mesh.inspect", max_triangles=5000, require_uvs=True, require_textures=True),
         _n("export", "asset.export", target_dir=str(tmp_path / "game" / "Assets"), filename="crate"),
         _n("reject", "data.template", template="rejected")],
        [_trig("gen"), _c("brief", "out", "gen", "prompt"), _c("gen", "mesh", "tex", "mesh"),
         _c("tex", "mesh", "check", "mesh"), _c("check", "pass", "export", "in"), _c("check", "fail", "reject", "in")],
    )
    res = WorkflowExecutor(wf).execute()
    assert res["ok"], res["node_errors"]
    assert res["node_status"]["export"] == "done" and res["node_status"]["reject"] == "skipped"
    exported = tmp_path / "game" / "Assets" / "crate.glb"
    assert exported.is_file() and glb.inspect_mesh(exported)["is_textured"]

    # Every produced asset knows the run, node and parent it came from.
    produced = store.list_assets(run_id=res["run_id"])["assets"]
    kinds = sorted(a["kind"] for a in produced)
    assert kinds == ["image", "mesh", "mesh"]       # raw mesh, textured mesh, extracted texture
    textured = res["node_outputs"]["tex"]["mesh"]
    raw = res["node_outputs"]["gen"]["mesh"]
    assert store.get(textured["id"])["parents"] == [raw["id"]]
    assert store.get(raw["id"])["source"]["node_id"] == "gen"
    assert store.get(raw["id"])["tags"] == ["crate", "test"]


def test_mesh_budget_failure_routes_to_fail_port():
    wf = _wf(
        [_n("t", "trigger.manual"), _n("gen", "model3d.generate", endpoint="demo:mesh", prompt="x"),
         _n("check", "mesh.inspect", max_triangles=4, require_textures=True),
         _n("good", "data.template", template="good"), _n("bad", "data.template", template="bad: {{input}}")],
        [_trig("gen"), _c("gen", "mesh", "check", "mesh"), _c("check", "pass", "good", "in"),
         _c("check", "issues", "bad", "in")],
    )
    res = WorkflowExecutor(wf).execute()
    assert res["node_status"]["good"] == "skipped"
    assert "exceeds the budget" in res["node_outputs"]["bad"]["out"]


# Executor: sub-workflows, loops, retries

def test_subworkflow_inputs_and_returns(isolated_storage):
    child = _wf(
        [_n("in", "flow.input", name="input"), _n("style", "global.text", name="style", value="plain"),
         _n("gen", "model3d.generate", endpoint="demo:mesh"),
         _n("ret", "flow.return", name="result"), _n("ret2", "flow.return", name="style_used")],
        [_c("in", "out", "gen", "prompt"), _c("gen", "mesh", "ret", "in"), _c("style", "out", "ret2", "in")],
        name="Make Prop", wf_id="wf_child")
    _save_wf(isolated_storage, child)
    parent = _wf(
        [_n("t", "trigger.manual"), _n("brief", "input.text", value="a barrel"),
         _n("call", "flow.subworkflow", workflow="Make Prop", variables='{"style": "low-poly"}')],
        [_trig("call"), _c("brief", "out", "call", "in")])
    res = WorkflowExecutor(parent).execute()
    assert res["ok"], res["node_errors"]
    out = res["node_outputs"]["call"]
    assert out["out"]["kind"] == "mesh"
    assert out["returns"]["style_used"] == "low-poly"
    # the child's assets carry the parent's run id
    assert store.get(out["out"]["id"])["source"]["run_id"] == res["run_id"]


def test_for_each_runs_once_per_item(isolated_storage):
    child = _wf([_n("in", "flow.input", name="item"), _n("tpl", "data.template", template="prop: {{input}}"),
                 _n("ret", "flow.return", name="result")],
                [_c("in", "out", "tpl", "in"), _c("tpl", "out", "ret", "in")], wf_id="wf_each")
    _save_wf(isolated_storage, child)
    parent = _wf(
        [_n("t", "trigger.manual"), _n("list", "input.list", items="crate\nbarrel\nchest"),
         _n("loop", "flow.for_each", workflow="wf_each", parallel=3)],
        [_trig("loop"), _c("list", "out", "loop", "items")])
    res = WorkflowExecutor(parent).execute()
    assert res["ok"], res["node_errors"]
    assert res["node_outputs"]["loop"]["results"] == ["prop: crate", "prop: barrel", "prop: chest"]
    assert res["node_outputs"]["loop"]["count"] == 3


def test_retry_until_passes_feedback_between_attempts(isolated_storage):
    # The child "passes" only on attempt 3, and reports feedback that the next attempt must see.
    child = _wf(
        [_n("attempt", "flow.input", name="attempt"), _n("fb", "flow.input", name="feedback", default="none"),
         _n("ok", "logic.if", condition="int(value) >= 3"),
         _n("yes", "data.template", template="true"), _n("no", "data.template", template="false"),
         _n("m", "logic.merge", mode="first"),
         _n("mkfb", "data.template", template="fix after attempt {{input}}"),
         _n("res", "data.template", template="made with feedback: {{input}}"),
         _n("r_pass", "flow.return", name="passed"), _n("r_fb", "flow.return", name="feedback"),
         _n("r_res", "flow.return", name="result")],
        [_c("attempt", "out", "ok", "in"), _c("ok", "true", "yes", "in"), _c("ok", "false", "no", "in"),
         _c("yes", "out", "m", "a"), _c("no", "out", "m", "b"), _c("m", "out", "r_pass", "in"),
         _c("attempt", "out", "mkfb", "in"), _c("mkfb", "out", "r_fb", "in"),
         _c("fb", "out", "res", "in"), _c("res", "out", "r_res", "in")],
        wf_id="wf_retry")
    _save_wf(isolated_storage, child)
    parent = _wf([_n("t", "trigger.manual"), _n("loop", "flow.retry_until", workflow="wf_retry", max_attempts=5),
                  _n("done", "data.template", template="shipped")],
                 [_trig("loop"), _c("loop", "pass", "done", "in")])
    res = WorkflowExecutor(parent).execute()
    assert res["ok"], res["node_errors"]
    out = res["node_outputs"]["loop"]
    assert out["passed"] is True and out["attempts"] == 3
    assert out["out"] == "made with feedback: fix after attempt 2"
    assert res["node_status"]["done"] == "done"

    parent["nodes"][1]["properties"]["max_attempts"] = 2
    res2 = WorkflowExecutor(parent).execute()
    assert res2["node_outputs"]["loop"]["passed"] is False
    assert res2["node_status"]["done"] == "skipped"


def test_recursive_subworkflow_is_stopped(isolated_storage):
    wf = _wf([_n("call", "flow.subworkflow", workflow="wf_loop")], [], wf_id="wf_loop")
    _save_wf(isolated_storage, wf)
    parent = _wf([_n("t", "trigger.manual"), _n("call", "flow.subworkflow", workflow="wf_loop")], [_trig("call")])
    res = WorkflowExecutor(parent).execute()
    assert not res["ok"] and "nested more than" in res["node_errors"]["call"]


# quality.verify — the reviewer model is stubbed so the routing logic is tested offline

class _StubReviewer:
    """Stands in for ProviderManager: records the call and returns a canned verdict."""

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def call_with_failover(self, **kwargs):
        self.calls.append(kwargs)

        class _Resp:
            success = True
            content = self.reply
            error = None
        return _Resp()


def _verify_wf():
    return _wf(
        [_n("t", "trigger.manual"), _n("brief", "input.text", value="a wooden crate"),
         _n("gen", "model3d.generate", endpoint="demo:mesh"),
         _n("tex", "model3d.texture", endpoint="demo:texture", prompt="oak"),
         _n("verify", "quality.verify", model="llm:any-vision-model", criteria="Game-ready crate.", threshold=70),
         _n("ship", "data.template", template="ship"), _n("redo", "data.template", template="redo: {{input}}")],
        [_trig("gen"), _c("brief", "out", "gen", "prompt"), _c("gen", "mesh", "tex", "mesh"),
         _c("tex", "mesh", "verify", "in"), _c("brief", "out", "verify", "context"),
         _c("verify", "pass", "ship", "in"), _c("verify", "feedback", "redo", "in")],
    )


def test_ai_verify_passes_and_sends_mesh_facts_and_textures(monkeypatch):
    import core.automate.nodes.models as models_mod
    stub = _StubReviewer('Sure! {"score": 88, "passed": true, "issues": [], "feedback": ""}')
    monkeypatch.setattr(models_mod, "_get_pm", lambda: stub)

    res = WorkflowExecutor(_verify_wf()).execute()
    assert res["ok"], res["node_errors"]
    out = res["node_outputs"]["verify"]
    assert out["passed"] is True and out["score"] == 88
    assert out["pass"]["kind"] == "mesh" and out["fail"] is None
    assert res["node_status"]["ship"] == "done"

    call = stub.calls[0]
    assert call["model"] == "any-vision-model"                   # llm: prefix stripped
    assert "12 triangles" in call["prompt"]                      # measured facts, not guesses
    assert "a wooden crate" in call["prompt"]                    # the brief, via Context
    assert len(call["images"]) == 1                              # the embedded texture, for vision models
    assert call["images"][0]["mime_type"] == "image/png"


def test_ai_verify_fails_below_threshold_and_routes_feedback(monkeypatch):
    import core.automate.nodes.models as models_mod
    stub = _StubReviewer('{"score": 40, "passed": true, "issues": ["Texture is a flat checker"], '
                         '"feedback": "Paint real wood grain."}')
    monkeypatch.setattr(models_mod, "_get_pm", lambda: stub)

    res = WorkflowExecutor(_verify_wf()).execute()
    out = res["node_outputs"]["verify"]
    assert out["passed"] is False            # the score decides, not the model's own "passed"
    assert out["fail"]["kind"] == "mesh" and out["pass"] is None
    assert res["node_status"]["ship"] == "skipped"
    assert res["node_outputs"]["redo"]["out"] == "redo: Paint real wood grain."


def test_ai_verify_reports_unusable_reviewer_reply(monkeypatch):
    import core.automate.nodes.models as models_mod
    monkeypatch.setattr(models_mod, "_get_pm", lambda: _StubReviewer("I think it looks fine."))
    res = WorkflowExecutor(_verify_wf()).execute()
    assert res["node_status"]["verify"] == "error"
    assert "did not return a verdict" in res["node_errors"]["verify"]


# Image node + "input never arrived" handling

def test_image_node_feeds_a_file_and_reuses_the_import(tmp_path):
    from PIL import Image
    pic = tmp_path / "concept.png"
    Image.new("RGB", (32, 16), "red").save(pic)
    wf = _wf([_n("t", "trigger.manual"), _n("img", "input.image", image=str(pic)),
              _n("gen", "model3d.generate", endpoint="demo:mesh")],
             [_trig("gen"), _c("img", "image", "gen", "image")])
    res = WorkflowExecutor(wf).execute()
    assert res["ok"], res["node_errors"]
    out = res["node_outputs"]["img"]
    assert out["image"]["kind"] == "image" and (out["width"], out["height"]) == (32, 16)
    # the mesh records the picture it was made from
    assert store.get(res["node_outputs"]["gen"]["mesh"]["id"])["parents"] == [out["image"]["id"]]
    # running again does not import the same file twice
    res2 = WorkflowExecutor(wf).execute()
    assert res2["node_outputs"]["img"]["image"]["id"] == out["image"]["id"]
    assert store.list_assets(kind="image")["total"] == 1


def test_step_is_skipped_not_failed_when_its_input_never_arrived():
    # Texture has a live prompt wire, but its mesh comes from a step that failed.
    wf = _wf(
        [_n("t", "trigger.manual"), _n("brief", "input.text", value="crate"),
         _n("gen", "model3d.generate", endpoint="does-not-exist"),
         _n("tex", "model3d.texture", endpoint="demo:texture"),
         _n("check", "mesh.inspect")],
        [_trig("gen"), _c("brief", "out", "gen", "prompt"), _c("gen", "mesh", "tex", "mesh"),
         _c("brief", "out", "tex", "prompt"), _c("tex", "mesh", "check", "mesh")],
    )
    res = WorkflowExecutor(wf).execute()
    assert list(res["node_errors"]) == ["gen"]            # one error: the real one
    assert res["node_status"]["tex"] == "skipped" and res["node_status"]["check"] == "skipped"


def test_trellis_source_patch_is_valid_and_idempotent(tmp_path):
    """The sdpa patch must produce parseable files and survive being applied twice."""
    import subprocess
    from core.interfaces.dashboard import trellis_patches as tp
    repo = tmp_path / "repo"
    attn = repo / "trellis" / "modules" / "sparse" / "attention"
    attn.mkdir(parents=True)
    head = ("from .. import DEBUG, ATTN\n\nif ATTN == 'xformers':\n    import xformers.ops as xops\n"
            "elif ATTN == 'flash_attn':\n    import flash_attn\nelse:\n"
            "    raise ValueError(f\"Unknown attention module: {ATTN}\")\n\n")
    (attn / "full_attn.py").write_text(
        head + "def f(s, out, N, L, H):\n    if ATTN == 'xformers':\n        pass\n"
        "    else:\n        raise ValueError(f\"Unknown attention module: {ATTN}\")\n    \n"
        "    if s is not None:\n        return s\n", encoding="utf-8")
    windowed = (head + "def g(qkv_feats, seq_lens, cu_seqlens, dense):\n    if dense:\n"
                "        if ATTN == 'flash_attn':\n"
                "            out = flash_attn.flash_attn_qkvpacked_func(qkv_feats)   # [B, N, H, C]\n"
                "        else:\n            raise ValueError(f\"Unknown attention module: {ATTN}\")\n"
                "    else:\n        if ATTN == 'flash_attn':\n"
                "            out = flash_attn.flash_attn_varlen_qkvpacked_func(qkv_feats, cu_seqlens, max(seq_lens)) # [M, H, C]\n"
                "\n    return out\n")
    (attn / "serialized_attn.py").write_text(windowed, encoding="utf-8")
    (attn / "windowed_attn.py").write_text(windowed, encoding="utf-8")
    (repo / "trellis" / "modules" / "sparse" / "__init__.py").write_text("x = ['xformers', 'flash_attn']\n", encoding="utf-8")
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"]):
        subprocess.run(cmd, cwd=repo, check=True)

    assert not tp.is_patched(repo)
    assert len(tp.apply_sdpa_patches(repo)) == 4
    assert tp.is_patched(repo)
    first = (attn / "full_attn.py").read_text(encoding="utf-8")
    tp.apply_sdpa_patches(repo)                                  # second run changes nothing
    assert (attn / "full_attn.py").read_text(encoding="utf-8") == first
    assert (chr(92) + "n") not in first.split("def f")[0]        # no literal backslash-n (the old bug)
    assert first.count("elif ATTN == 'sdpa':") == 2
