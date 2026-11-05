"""HSPiP discovery stays inside Program Files and leaves the form blank on a miss."""

from packages.doss_core.hspip import (
    default_hspip_data_raw,
    default_hspip_exe_raw,
    discover_sofx_dir,
    find_hspip_install,
    hspip_missing_prompt,
)


def test_finds_hspip_exe_under_a_hansen_folder(tmp_path):
    install = tmp_path / "Hansen-Solubility-6" / "HSPiP"
    install.mkdir(parents=True)
    (install / "HSPiP.exe").write_bytes(b"x")
    unrelated = tmp_path / "Some Other App"
    unrelated.mkdir()
    (unrelated / "HSPiP.exe").write_bytes(b"x")

    assert find_hspip_install([tmp_path]) == install


def test_sofx_beside_the_exe_wins(tmp_path):
    (tmp_path / "solvents.sofx").write_text("<lib/>", encoding="utf-8")
    assert discover_sofx_dir(tmp_path) == tmp_path


def test_sofx_in_a_subfolder(tmp_path):
    data = tmp_path / "Data"
    data.mkdir()
    (data / "solvents.sofx").write_text("<lib/>", encoding="utf-8")
    assert discover_sofx_dir(tmp_path) == data


def test_prompt_asks_for_the_exe_folder_when_discovery_misses():
    text = hspip_missing_prompt("", "", False)
    assert "Paste the folder that contains HSPiP.exe" in text
    assert r"C:\Program Files\Hansen-Solubility-6\HSPiP" in text


def test_prompt_asks_for_sofx_when_only_the_exe_was_found():
    text = hspip_missing_prompt(r"C:\Program Files\Hansen-Solubility-6\HSPiP", "", True)
    assert "no .sofx files" in text
    assert hspip_missing_prompt(r"C:\HSPiP", r"C:\HSPiP", True) == ""


def test_defaults_fill_from_discovery(monkeypatch, tmp_path):
    install = tmp_path / "HSPiP"
    install.mkdir()
    (install / "HSPiP.exe").write_bytes(b"x")
    (install / "solvents.sofx").write_text("<lib/>", encoding="utf-8")
    monkeypatch.setattr("packages.doss_core.hspip.load_saved_hspip_paths", lambda: {})
    monkeypatch.setattr(
        "packages.doss_core.hspip.discover_hspip_install_dir", lambda: install
    )
    for key in ("HSPIP_EXE", "HSPIP_PATH", "HSPIP_DATA", "HSPIP_DATA_DIR"):
        monkeypatch.delenv(key, raising=False)

    assert default_hspip_exe_raw() == str(install)
    assert default_hspip_data_raw() == str(install)


def test_defaults_stay_blank_when_nothing_is_installed(monkeypatch, tmp_path):
    empty = tmp_path / "HSPiP"
    empty.mkdir()
    monkeypatch.setattr(
        "packages.doss_core.hspip.load_saved_hspip_paths",
        lambda: {"exe": str(empty), "data": str(empty)},
    )
    monkeypatch.setattr(
        "packages.doss_core.hspip.discover_hspip_install_dir", lambda: None
    )
    for key in ("HSPIP_EXE", "HSPIP_PATH", "HSPIP_DATA", "HSPIP_DATA_DIR"):
        monkeypatch.delenv(key, raising=False)

    assert default_hspip_exe_raw() == ""
    assert default_hspip_data_raw() == ""
