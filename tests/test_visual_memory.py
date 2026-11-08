import tempfile
from pathlib import Path
from PIL import Image
from core.companions.engine.visual_memory import CompanionVisualMemory
from core.bridges import bridge_manager


def test_visual_memory_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        vmem = CompanionVisualMemory(p, "Misaka Cipher")

        # Create a sample mock image to test remember with image_path
        sample_img = p / "test_sample.png"
        img = Image.new("RGB", (1920, 1080), color=(73, 109, 137))
        img.save(sample_img)

        # 1. Test remember Unity layout
        r1 = vmem.remember(
            title="Unity Main Level Hierarchy & Inspector",
            category="unity",
            description="PlayerRoot prefab selected, LevelLighting component active, 3 UI canvas panels on left.",
            key_elements=["PlayerRoot", "LevelLighting", "MainCanvas", "HierarchyPanel"],
            image_path=str(sample_img),
            tags=["level-design", "unity", "lighting"]
        )
        assert r1.get("status") == "saved"
        m1 = r1["memory"]
        assert m1["title"] == "Unity Main Level Hierarchy & Inspector"
        assert m1["category"] == "unity"
        assert m1["width"] == 1920
        assert m1["height"] == 1080
        assert Path(m1["image_path"]).exists()

        # 2. Test remember Blender 3D Model
        r2 = vmem.remember(
            title="Blender Cyber Katana Hilt Mesh",
            category="blender",
            description="Subdivision level 2 on hilt guard, mirror modifier applied, UV unwrap completed.",
            key_elements=["HiltGuard", "BladeRoot", "MirrorModifier"],
            image_path=str(sample_img),
            tags=["blender", "weapon", "cyberpunk"]
        )
        assert r2.get("status") == "saved"

        # 3. Test load
        loaded = vmem.load()
        assert loaded["total"] == 2
        assert loaded["category_counts"]["unity"] == 1
        assert loaded["category_counts"]["blender"] == 1
        assert len(loaded["memories"]) == 2

        # 4. Test search
        res_unity = vmem.search(query="katana")
        assert len(res_unity) == 1
        assert "Katana" in res_unity[0]["title"]

        res_cat = vmem.search(category="unity")
        assert len(res_cat) == 1
        assert res_cat[0]["category"] == "unity"

        # 5. Test context summary
        summary = vmem.get_recent_summary_for_context(limit=3)
        assert "VISUAL CONTEXT MEMORY ON FILE:" in summary
        assert "Unity Main Level" in summary
        assert "Blender Cyber Katana" in summary

        # 6. Test compare
        comp_res = vmem.compare(query="unity", current_image_path=str(sample_img))
        assert comp_res.get("status") == "ready_to_compare"
        assert comp_res["reference_memory"]["category"] == "unity"
        assert Path(comp_res["current_image_path"]).exists()

        # 7. Test update
        upd = vmem.update(m1["id"], {"description": "Updated note: lighting adjusted to warm sunset."})
        assert upd is not None
        assert "lighting adjusted" in upd["description"]

        # 8. Test delete
        saved_file = Path(m1["image_path"])
        del_ok = vmem.delete(m1["id"])
        assert del_ok is True
        assert not saved_file.exists(), "Snapshot file should be cleaned up on delete"

        after_del = vmem.load()
        assert after_del["total"] == 1

        print("VISUAL MEMORY UNIT TESTS PASSED PERFECTLY!")


def test_bridge_connector():
    from core.bridges import visual_memory_bridge

    # Test list_memories through bridge connector
    out = visual_memory_bridge.list_memories({"limit": 5})
    assert isinstance(out, str)

    # Test recall through bridge connector
    out_recall = visual_memory_bridge.recall({"query": "layout"})
    assert isinstance(out_recall, str)

    print("VISUAL MEMORY BRIDGE CONNECTOR TESTS PASSED PERFECTLY!")


if __name__ == "__main__":
    test_visual_memory_lifecycle()
    test_bridge_connector()
