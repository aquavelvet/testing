import sys

import pytest

from recipebook import cli


@pytest.fixture
def mac(tmp_path, monkeypatch):
    folder = tmp_path / "homebrew" / "lib"
    folder.mkdir(parents=True)
    calls = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(cli, "HOMEBREW_LIBRARY_FOLDERS", (str(folder), str(tmp_path / "missing")))
    monkeypatch.setattr(cli.os, "execv", lambda exe, args: calls.append((exe, args, cli.os.environ["DYLD_FALLBACK_LIBRARY_PATH"])))
    monkeypatch.delenv("DYLD_FALLBACK_LIBRARY_PATH", raising=False)
    return folder, calls


def test_restarts_once_with_homebrew_on_the_library_path(mac):
    folder, calls = mac
    (folder / "libgobject-2.0.0.dylib").write_bytes(b"")
    cli.ensure_homebrew_libraries(["doctor"])
    assert calls == [(sys.executable, [sys.executable, "-m", "recipebook.cli", "doctor"], str(folder))]
    cli.ensure_homebrew_libraries(["doctor"])  # the path is now set, as it would be after the restart
    assert len(calls) == 1


def test_keeps_a_path_the_user_already_set(mac, monkeypatch):
    folder, calls = mac
    (folder / "libgobject-2.0.0.dylib").write_bytes(b"")
    monkeypatch.setenv("DYLD_FALLBACK_LIBRARY_PATH", "/custom/lib")
    cli.ensure_homebrew_libraries(["serve", "--port", "9000"])
    assert calls[0][2] == f"{folder}:/custom/lib" and calls[0][1][-3:] == ["serve", "--port", "9000"]


def test_does_nothing_without_pango_or_off_the_mac(mac, monkeypatch):
    _, calls = mac
    cli.ensure_homebrew_libraries([])  # Homebrew folder exists but Pango is not installed
    monkeypatch.setattr(sys, "platform", "linux")
    cli.ensure_homebrew_libraries([])
    assert calls == []
