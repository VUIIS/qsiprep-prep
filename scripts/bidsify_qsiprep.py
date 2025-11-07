#!/usr/bin/env python3
"""
XNAT-friendly BIDSify for QSIPrep (single subject) — FLAT INPUTS ONLY

- All INPUT files arrive in ONE flat directory (no DWI/fmap/T1w subfolders).
  Examples that may be present:
    dwi_1000.nii.gz, .bval, .bvec, .json      (AP, e.g., "...b1000app...")
    dwi_2000.nii.gz, .bval, .bvec, .json      (AP, e.g., "...b2000app...")
    901_dti_2min_b1000apa_fov140.nii.gz, ...  (PA; used as fieldmap image)
    t1.nii.gz, t1.json
    SUBJECT/ or SUBJECT/SUBJECT (FreeSurfer dir; copied verbatim to OUTPUTS/SUBJECT)

Behavior (locked in):
- EVERYTHING is written under --outputs-dir.
- We stage from the flat folder into OUTPUTS/INPUTS/{DWI,fmap,T1w}:
    DWI  := any NIfTI inferred as AP (dir token 'AP' from filename hints)
    FMAP := any NIfTI inferred as PA (dir token 'PA' from filename hints; e.g., "*apa*")
    T1w  := files named "t1.nii.gz" / "t1.json"
- Build BIDS under OUTPUTS/BIDS/sub-<id>/ with strict names:
    DWI  -> sub-<id>_acq-b<shell>_dir-AP_dwi.*
    FMAP -> sub-<id>_acq-b<shell>_dir-PA_epi.* (ALWAYS placed in BIDS/fmap)
    T1w  -> sub-<id>_T1w.*
- JSON fixes:
    * EstimatedTotalReadoutTime -> TotalReadoutTime (if present)
    * Add PhaseEncodingDirection if missing (AP->j-, PA->j, LR/RL/SI/IS supported via map)
    * FMAP JSON gets IntendedFor with all subject DWI NIfTIs (relative paths)
- Subject label is provided via --subject and sanitized to BIDS-safe (alphanumeric only).
- Write dataset_description.json and participants.tsv in BIDS root.
- Write mapping OUTPUTS/bids_subject_map.tsv: xnat_subject <TAB> bids_subject
"""

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Optional, Tuple

# ------------- helpers -------------
def sanitize_bids_subj(raw_label: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9]+', '', raw_label)
    return cleaned or "UNKNOWN"

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def copy_file(src: Path, dst: Path):
    ensure_dir(dst.parent); shutil.copy2(src, dst)

def load_json(p: Path) -> dict:
    with p.open('r') as f: return json.load(f)

def save_json(p: Path, obj: dict):
    ensure_dir(p.parent)
    with p.open('w') as f:
        json.dump(obj, f, indent=2, sort_keys=True); f.write('\n')

PED_MAP = {"AP":"j-","PA":"j"}
DIR_TOKEN_RE  = re.compile(r"(?:^|[_-])dir-([A-Za-z]{2})(?:[_-]|$)", re.IGNORECASE)
BVAL_TOKEN_RE = re.compile(r"(?:^|[_-])b(\d{3,5})(?:[^0-9]|$)", re.IGNORECASE)
ALT_DIR_HINTS = {"app":"AP","apa":"PA","_ap_":"AP","-ap-":"AP","_pa_":"PA","-pa-":"PA"}

def find_dir_from_name(path: Path) -> Optional[str]:
    m = DIR_TOKEN_RE.search(path.name)
    if m: return m.group(1).upper()
    low = f"_{path.name.lower()}_"
    for hint,val in ALT_DIR_HINTS.items():
        if hint in low: return val
    return None

def infer_ped_from_dir(dir_token: Optional[str]) -> Optional[str]:
    return PED_MAP.get(dir_token.upper()) if dir_token else None

def infer_primary_bval_from_bvalfile(bval_path: Path) -> Optional[str]:
    if not bval_path.exists(): return None
    try:
        vals = [float(x) for x in re.split(r"\s+", bval_path.read_text().strip()) if x.strip()]
        nz   = [int(round(v)) for v in vals if v > 10]
        if not nz: return "0"
        from collections import Counter
        return str(Counter(nz).most_common(1)[0][0])
    except Exception:
        return None

def strict_dwi_bids_name(subj,bval,dir_token,suffix):  return f"{subj}_acq-b{bval}_dir-{dir_token}_dwi{suffix}"
def strict_fmap_bids_name(subj,bval,dir_token,suffix): return f"{subj}_acq-b{bval}_dir-{dir_token}_epi{suffix}"
def strict_t1w_bids_name(subj,suffix):                  return f"{subj}_T1w{suffix}"

# ------------- JSON edits -------------
def update_dwi_json(json_path: Path, ped: Optional[str]):
    meta = load_json(json_path)
    if "EstimatedTotalReadoutTime" in meta:
        if not meta.get("TotalReadoutTime"):
            meta["TotalReadoutTime"] = meta["EstimatedTotalReadoutTime"]
        del meta["EstimatedTotalReadoutTime"]
    if ("PhaseEncodingDirection" not in meta) or (str(meta.get("PhaseEncodingDirection","")).strip()==""):
        if ped: meta["PhaseEncodingDirection"] = ped
    save_json(json_path, meta)

def update_fmap_json(json_path: Path, ped: Optional[str], intended_files: list[str]):
    meta = load_json(json_path)
    if "EstimatedTotalReadoutTime" in meta:
        if not meta.get("TotalReadoutTime"):
            meta["TotalReadoutTime"] = meta["EstimatedTotalReadoutTime"]
        del meta["EstimatedTotalReadoutTime"]
    meta["IntendedFor"] = intended_files
    if ("PhaseEncodingDirection" not in meta) or (str(meta.get("PhaseEncodingDirection","")).strip()==""):
        if ped: meta["PhaseEncodingDirection"] = ped
    save_json(json_path, meta)

# ------------- Stage from FLAT → OUTPUTS/INPUTS/... -------------
def stage_from_flat_inputs(inputs_dir: Path, outputs_dir: Path) -> Tuple[Path,Path,Path,Optional[Path]]:
    dwi_out  = outputs_dir / "INPUTS" / "DWI"
    fmap_out = outputs_dir / "INPUTS" / "fmap"
    t1_out   = outputs_dir / "INPUTS" / "T1w"
    for d in (dwi_out,fmap_out,t1_out): ensure_dir(d)

    # DWI = AP
    for nii in sorted(inputs_dir.glob("*.nii.gz")):
        if nii.name.lower().startswith("t1"): continue
        if find_dir_from_name(nii) == "AP":
            base = nii.name[:-7]
            for ext in [".nii.gz",".bval",".bvec",".json"]:
                src = inputs_dir / (base + ext)
                if src.exists(): copy_file(src, dwi_out / src.name)

    # FMAP = PA (will always end up in BIDS/fmap)
    for nii in sorted(inputs_dir.glob("*.nii.gz")):
        if nii.name.lower().startswith("t1"): continue
        if find_dir_from_name(nii) == "PA":
            base = nii.name[:-7]
            for ext in [".nii.gz",".bval",".bvec",".json"]:
                src = inputs_dir / (base + ext)
                if src.exists(): copy_file(src, fmap_out / src.name)

# T1: accept any NIfTI whose name contains "t1" (case-insensitive)
    t1_candidates = sorted([p for p in inputs_dir.glob("*.nii.gz")
    if "t1" in p.name.lower() and not p.name.lower().startswith("t1map")])
    if t1_candidates:
        t1_src = t1_candidates[0]          # pick the first if multiple; change policy if needed
        copy_file(t1_src, t1_out / "t1.nii.gz")
        # companion JSON with same base (if present)
        t1_json_src = t1_src.with_suffix("").with_suffix(".json")
    if t1_json_src.exists():
        copy_file(t1_json_src, t1_out / "t1.json")
    else:
        print("[warn] No T1 found in flat INPUTS (looked for *t1*.nii.gz)")

    # FreeSurfer SUBJECT or SUBJECT/SUBJECT
    fs_candidate = inputs_dir / "SUBJECT"
    if fs_candidate.is_dir():
        nested = fs_candidate / "SUBJECT"
        fs_src = nested if nested.is_dir() else fs_candidate
        fs_dst = outputs_dir / "SUBJECT"
        if fs_dst.exists(): shutil.rmtree(fs_dst)
        shutil.copytree(fs_src, fs_dst)
        fs_out = fs_dst
    else:
        fs_out = None

    return dwi_out, fmap_out, t1_out, fs_out

# ------------- Build BIDS -------------
def bidsify(outputs_dir: Path, subj_raw: str):
    subj_clean = sanitize_bids_subj(subj_raw)
    subj = f"sub-{subj_clean}"
    bids_root = outputs_dir / "BIDS"
    subj_root = bids_root / subj
    dwi_in  = outputs_dir / "INPUTS" / "DWI"
    fmap_in = outputs_dir / "INPUTS" / "fmap"
    t1_in   = outputs_dir / "INPUTS" / "T1w"
    for d in (subj_root/"dwi", subj_root/"fmap", subj_root/"anat"): ensure_dir(d)

    intended_for = []

    # DWI → BIDS/dwi
    for nii in sorted(dwi_in.glob("*.nii.gz")):
        base = nii.name[:-7]
        bval = infer_primary_bval_from_bvalfile(dwi_in / (base + ".bval")) or \
               (BVAL_TOKEN_RE.search(nii.name).group(1) if BVAL_TOKEN_RE.search(nii.name) else "0")
        dir_token = "AP"
        ped = infer_ped_from_dir(dir_token)
        out_name = strict_dwi_bids_name(subj, bval, dir_token, ".nii.gz")
        copy_file(nii, subj_root / "dwi" / out_name)
        for ext in [".bval",".bvec",".json"]:
            src = dwi_in / (base + ext)
            dst = subj_root / "dwi" / strict_dwi_bids_name(subj, bval, dir_token, ext)
            if src.exists():
                copy_file(src, dst)
                if ext == ".json": update_dwi_json(dst, ped)
            elif ext == ".json":
                save_json(dst, {"PhaseEncodingDirection": ped} if ped else {})
        intended_for.append(f"dwi/{out_name}")

    # FMAP → ALWAYS BIDS/fmap as *_epi.*
    for fmap_nii in sorted(fmap_in.glob("*.nii.gz")):
        base = fmap_nii.name[:-7]
        bval = infer_primary_bval_from_bvalfile(fmap_in / (base + ".bval")) or \
               (BVAL_TOKEN_RE.search(fmap_nii.name).group(1) if BVAL_TOKEN_RE.search(fmap_nii.name) else "1000")
        dir_token = "PA"
        ped = infer_ped_from_dir(dir_token)
        out_name = strict_fmap_bids_name(subj, bval, dir_token, ".nii.gz")
        copy_file(fmap_nii, subj_root / "fmap" / out_name)
        src_json = fmap_in / (base + ".json")
        dst_json = subj_root / "fmap" / strict_fmap_bids_name(subj, bval, dir_token, ".json")
        if src_json.exists():
            copy_file(src_json, dst_json); update_fmap_json(dst_json, ped, intended_for)
        else:
            meta = {"IntendedFor": intended_for}
            if ped: meta["PhaseEncodingDirection"] = ped
            save_json(dst_json, meta)

    # T1w
    t1 = t1_in / "t1.nii.gz"
    if t1.exists():
        copy_file(t1, subj_root / "anat" / strict_t1w_bids_name(subj, ".nii.gz"))
        t1_json = t1_in / "t1.json"
        if t1_json.exists():
            copy_file(t1_json, subj_root / "anat" / strict_t1w_bids_name(subj, ".json"))

    # Dataset-level files
    save_json(bids_root / "dataset_description.json", {"Name":"BIDS dataset","BIDSVersion":"1.9.0","DatasetType":"raw"})
    part_tsv = bids_root / "participants.tsv"
    if part_tsv.exists():
        old = set(x.strip() for x in part_tsv.read_text().splitlines()[1:] if x.strip()); old.add(subj)
        rows = sorted(old)
    else:
        rows = [subj]
    with part_tsv.open("w") as f:
        f.write("participant_id\n"); [f.write(f"{r}\n") for r in rows]

    # Subject map
    map_path = outputs_dir / "bids_subject_map.tsv"
    if map_path.exists():
        lines = [ln.strip().split("\t") for ln in map_path.read_text().splitlines() if ln.strip()]
        header = lines[0] if lines else ["xnat_subject","bids_subject"]
        existing = {tuple(row) for row in lines[1:]} if len(lines)>1 else set()
        existing.add((subj_raw, subj)); pairs = sorted(existing)
    else:
        header = ["xnat_subject","bids_subject"]; pairs = [(subj_raw, subj)]
    with map_path.open("w") as f:
        f.write("\t".join(header) + "\n")
        for a,b in pairs: f.write(f"{a}\t{b}\n")

# ------------- CLI -------------
def main():
    ap = argparse.ArgumentParser(description="BIDSify QSIPrep inputs from a SINGLE FLAT INPUTS directory (XNAT-style).")
    ap.add_argument("--inputs-dir", required=True, help="Flat INPUTS dir (all files together)")
    ap.add_argument("--outputs-dir", required=True, help="OUTPUTS dir (all artifacts go here)")
    ap.add_argument("--subject", required=True, help="XNAT subject label (sanitized to BIDS)")
    args = ap.parse_args()
    inputs_dir  = Path(args.inputs_dir).resolve()
    outputs_dir = Path(args.outputs_dir).resolve()
    stage_from_flat_inputs(inputs_dir, outputs_dir)
    bidsify(outputs_dir, args.subject)

if __name__ == "__main__":
    main()
