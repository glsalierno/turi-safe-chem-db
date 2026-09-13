# HSPiP CLI & sofx cache

## Install HSPiP + CLI license

1. Install HSPiP from [hansen-solubility.com](https://www.hansen-solubility.com/HSPiP).
2. Ensure your license includes **CLI** (Command Line Interface). Contact HSPiP support if unsure.
3. Set `HSPIP_PATH` to the install folder (example: `C:\Program Files\Hansen-Solubility\HSPiP` or `...\Hansen-Solubility-6\HSPiP`), or `HSPIP_EXE` to `HSPiP.exe` itself.

**TURI Safe Chem DB never ships `HSPiP.exe`.** You must install it yourself.

## In-app path prompt (DoSS Streamlit)

The sidebar **HSPiP setup** section:

1. Short due-diligence note (self-install, CLI license for new CAS, no shipped binary, close GUI before CLI).
2. Text input for the path to `HSPiP.exe` **or** the install folder. Defaults from env `HSPIP_PATH` / `HSPIP_EXE`, then a saved local config.
3. Paths persist in `st.session_state` and a small local file:
   - repo-local `config/hspip_path.txt` (gitignored)
   - `~/.turi-safe-chem-db/hspip_path.txt`
4. Validation: if the path is a directory, the app looks for `HSPiP.exe` inside; if it is a file, the name must be `HSPiP.exe`. Status shows ✅ or ❌.
5. Separate **HSPIP_DATA** input for `.sofx` libraries (default: env `HSPIP_DATA` / `HSPIP_DATA_DIR`, or the Teams pack `HSPiP_Data` folder).
6. When a CAS misses sofx (`needs_HSPiP`), the coverage panel captions: *"Provide HSPiP.exe above to compute new CAS via CLI"* and offers **Compute HSP via CLI** (if the exe path is valid).
7. Optional checkbox **Auto-run CLI when CAS misses sofx** — **default OFF**.
8. CLI hook (`packages.doss_core.hspip.compute_hsp_via_cli`) runs `HSPiP.exe Y-MBSX <SMILES>` in the install directory and parses `Out.dat` for D/P/H (same pattern as `vendors/cas_to_hspip/HSPiP_CLI_v7.py`). SMILES comes from PubChem. **D/P/H are never invented** — parse failure is an error.

## sofx libraries (preferred for DoSS)

DoSS fills D/P/H/RER from local `.sofx` solvent tables — **no CLI required** when the CAS hits.

```bat
set HSPIP_DATA=C:\path\to\HSPiP Data
rem alias also accepted:
set HSPIP_DATA_DIR=C:\path\to\HSPiP Data
```

Prefer sofx cache via `HSPIP_DATA` over calling the CLI for interactive DoSS lookups.

## CLI glue (open wrappers)

Open scripts live in `vendors/cas_to_hspip/`:

- `HSPiP_CLI_v7.py` — batch SMILES → HSP via HSPiP CLI
- `get_smiles_InChI_IUPAC_props.py` — PubChem identity/props
- `CAS2SMILES2HSPiP.m` — MATLAB bridge

Update paths in those scripts (or set `HSPIP_PATH`) before running. See that folder's README.

## Operational tips

- **Close the HSPiP GUI** before running CLI jobs (GUI and CLI contend for locks).
- **Out.dat / clipboard lock**: CLI can fail if a previous run left Out.dat locked or if clipboard automation is blocked — retry after closing HSPiP and clearing stuck processes.
- Do **not** commit `HSPiP.exe`, license files, or `*.sofx` into git or the Teams pack app tree; use the placeholder folders in the Teams pack.
- In-app CLI is **opt-in** (button or checkbox). A timeout or unreadable `Out.dat` leaves D/P/H as `needs_HSPiP`.
