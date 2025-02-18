# tests/test_cli.py
import json
import tempfile
from mytool.context import load_context, ContextData

def test_load_context_valid():
    # Prepare valid context data.
    data = {"name": "TestUser", "verbose": True}
    with tempfile.NamedTemporaryFile("w+", delete=False) as tmp:
        json.dump(data, tmp)
        tmp_path = tmp.name

    context = load_context(tmp_path)
    assert isinstance(context, ContextData)
    assert context.name == "TestUser"
    assert context.verbose is True
