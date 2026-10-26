"""Write src/lib/__fixtures__/run_input_parity.json FROM the desktop's builder.

Each case is the SAME keyword arguments given to
abstractassistant.gateway.run_input.build_run_input_data and to the web's
buildRunInputData (src/lib/run_input.ts); `expected` is what Python returned.
Re-run after changing either builder:

    PYTHONPATH=. python -P web/scripts/gen_run_input_parity.py   # from the repository root

(PYTHONPATH=. makes it read THIS checkout's run_input.py, whatever is
installed; -P keeps web/scripts/ itself off sys.path.)
"""

import json
import pathlib

from abstractassistant.gateway.run_input import build_run_input_data

IMG = {"$artifact": "a1", "content_type": "image/png", "filename": "shot.png", "run_id": "session_memory_s1"}
PDF = {"$artifact": "a2", "content_type": "application/pdf", "filename": "cv.pdf", "run_id": "session_memory_s1"}

CASES = [
    ("bare prompt", {"prompt": "hello"}),
    ("system and session history off", {"prompt": "hi", "system": "be brief", "use_session_history": False}),
    ("override rides both channels", {"prompt": "hi", "provider": "lmstudio", "model": "m", "base_url": "http://localhost:1234/v1"}),
    ("half pin dropped (provider only)", {"prompt": "hi", "provider": "lmstudio"}),
    ("half pin dropped (model only)", {"prompt": "hi", "model": "m"}),
    ("base_url alone dropped", {"prompt": "hi", "base_url": "http://x"}),
    ("local messages ignored without use_context", {"prompt": "hi", "messages": [{"role": "user", "content": "old"}]}),
    ("messages with use_context", {"prompt": "hi", "use_context": True, "messages": [
        {"role": "user", "content": "old"}, {"role": "tool", "content": "x"}, {"role": "assistant", "content": "  "},
        {"role": "assistant", "content": "answer"}]}),
    ("attachments and primary image", {"prompt": "look", "attachments": [IMG, PDF, {"filename": "no-ref"}], "primary_image_artifact": IMG}),
    ("primary image without ref ignored", {"prompt": "look", "primary_image_artifact": {"filename": "x"}}),
    ("thinking stream workspace", {"prompt": "hi", "thinking": " High ", "stream": True, "workspace_root": " /tmp/w "}),
    ("stream false", {"prompt": "hi", "stream": False}),
    ("tools temperature seed iterations", {"prompt": "hi", "allowed_tools": [" web_search ", "", "fetch_url"], "temperature": 0.2, "seed": 7, "max_iterations": 0}),
    ("empty allowed tools", {"prompt": "hi", "allowed_tools": []}),
    ("tool policy lists", {"prompt": "hi", "tool_policy": {"auto_approve_tools": "read_file, list_files", "requireApproval": ["execute_command"]}}),
    ("tool policy empty", {"prompt": "hi", "tool_policy": {"auto_approve_tools": []}}),
]

out = [{"name": name, "args": args, "expected": build_run_input_data(**args)} for name, args in CASES]
target = pathlib.Path(__file__).resolve().parent.parent / "src" / "lib" / "__fixtures__" / "run_input_parity.json"
target.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {len(out)} cases to {target}")
