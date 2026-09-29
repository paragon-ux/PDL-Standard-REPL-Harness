"""Tests for pdlt viewer CLI subcommand and REPL /viewer slash command."""

import json
import urllib.request
import pytest
from pdl_taskmaster.host.cli import main as cli_main
from pdl_taskmaster.tools.viewer_server import start_server, get_catalogue_summary, get_session_telemetry


def test_viewer_server_endpoints():
    thread, server, port = start_server(8095)
    try:
        base_url = f"http://127.0.0.1:{port}"
        
        # Test index page serving
        req = urllib.request.Request(f"{base_url}/")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            content = resp.read().decode("utf-8")
            assert "<title>PDLt Live REPL Viewer & Telemetry Dashboard</title>" in content
            
        # Test API status endpoint
        req = urllib.request.Request(f"{base_url}/api/status")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "session_id" in data
            assert "stage" in data
            
        # Test API catalogue endpoint
        req = urllib.request.Request(f"{base_url}/api/catalogue")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            cat_data = json.loads(resp.read().decode("utf-8"))
            assert isinstance(cat_data, list)
    finally:
        server.shutdown()
        server.server_close()


def test_cli_viewer_dispatch(monkeypatch):
    called = {}

    def fake_main(argv):
        called["argv"] = argv
        return 0

    monkeypatch.setattr("pdl_taskmaster.tools.viewer_server.main", fake_main)
    ret = cli_main(["viewer", "--no-open"])
    assert ret == 0
    assert called["argv"] == ["--no-open"]
