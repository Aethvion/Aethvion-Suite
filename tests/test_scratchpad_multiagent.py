import tempfile
from pathlib import Path
from core.companions.engine.scratchpad import CompanionScratchpad

def test_multiagent_scratchpad():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        sp = CompanionScratchpad(p, 'Misaka Cipher')
        
        # 1. Append notes with distinct authors
        sp.append_note('First idea', section='Ideas', author={'id':'marcel','name':'Marcel','role':'user','color':'#10b981'})
        sp.append_note('Second idea', section='Ideas', author='misakacipher')
        sp.append_note('Third idea', section='Mechanics', author={'id':'agent-coder','name':'Coder Agent','role':'agent','color':'#3b82f6'})
        
        loaded = sp.load()
        assert len(loaded['entries']) == 3
        assert len(loaded['authors']) == 3
        
        # 2. Reconcile manual edits: edit one item, delete one item, add an unbadged item
        edited_md = (
            "# Shared Brainstorming Scratchpad\n\n"
            "## 💡 Ideas & Brainstorming\n"
            "- <span class=\"spad-author-pill\" data-author-id=\"misakacipher\" data-author=\"Misaka Cipher\" "
            "data-color=\"#6366f1\" data-time=\"2026-11-08T10:00:00Z\" data-role=\"companion\">✦ Misaka</span> Second idea (edited)\n"
            "- Brand new idea typed by Marcel without badge\n"
        )
        res = sp.save(edited_md)
        entries = res['entries']
        assert len(entries) == 2
        # First entry kept its Misaka attribution
        assert entries[0]['author']['id'] == 'misakacipher'
        assert entries[0]['text'] == 'Second idea (edited)'
        # Second entry automatically attributed to Marcel
        assert entries[1]['author']['id'] == 'marcel'
        assert entries[1]['text'] == 'Brand new idea typed by Marcel without badge'
        print('MULTIAGENT SCRATCHPAD TEST PASSED PERFECTLY!')


def test_scratchpad_block_comments_and_delete():
    with tempfile.TemporaryDirectory() as tmpdir:
        sp = CompanionScratchpad(Path(tmpdir), 'Group')
        initial = sp.load()
        assert initial['entries'] == []
        assert initial['sections'] == []

        appended = sp.append_note('Add timeline scrubber', section='Architecture', author='Marcel')
        entry_id = appended['entry']['id']

        commented = sp.add_comment(entry_id, 'Looks clean!', author='Marcel')
        assert len(commented['entries']) == 1
        assert len(commented['entries'][0]['comments']) == 1
        assert commented['entries'][0]['comments'][0]['text'] == 'Looks clean!'

        after_delete = sp.delete_entry(entry_id)
        assert after_delete['entries'] == []

if __name__ == '__main__':
    test_multiagent_scratchpad()
