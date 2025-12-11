#!/usr/bin/env python3
"""
XNAT-friendly BIDSify for QSIPrep (single session)
"""

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Optional, Tuple

# ------------- helpers -------------
def sanitize_bids_label(raw_label: str) -> str:
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

def strict_dwi_bids_name(subj, sess, acq_token, dir_token, ext):
    return f"{subj}_{sess}_acq-{acq_token}_dir-{dir_token}_dwi{ext}"

def strict_t1w_bids_name(subj, sess, ext):
    return f"{subj}_{sess}_T1w{ext}"


# ------------- JSON edits -------------
def update_dwi_json(json_path: Path, reverse_pedir: Optional[bool]):
    meta = load_json(json_path)
    if "EstimatedTotalReadoutTime" in meta:
        if not meta.get("TotalReadoutTime"):
            meta["TotalReadoutTime"] = meta["EstimatedTotalReadoutTime"]
        del meta["EstimatedTotalReadoutTime"]
    if ("PhaseEncodingDirection" not in meta) or (str(meta.get("PhaseEncodingDirection","")).strip()==""):
        if ("PhaseEncodingAxis" not in meta) or (str(meta.get("PhaseEncodingAxis","")).strip()==""):
            raise Exception("Did not find PhaseEncodingAxis to determine PhaseEncodingDirection")
        meta["PhaseEncodingDirection"] = meta["PhaseEncodingAxis"]
        if reverse_pedir:
            if "-" in meta["PhaseEncodingDirection"]:
                meta["PhaseEncodingDirection"] = meta["PhaseEncodingDirection"].replace("-","")
            else:
                meta["PhaseEncodingDirection"] = meta["PhaseEncodingDirection"] + "-"
    save_json(json_path, meta)


# ------------- Build BIDS -------------
def bidsify(args: argparse.Namespace):
    
    subj_clean = sanitize_bids_label(args.subject_label)
    sess_clean = sanitize_bids_label(args.session_label)
    subj = f"sub-{subj_clean}"
    sess = f"ses-{sess_clean}"
    bids_root = Path(args.out_dir).resolve()
    sess_root = bids_root / subj / sess
    for d in (sess_root/"dwi", sess_root/"anat"): ensure_dir(d)

    # DWI → BIDS/dwi
    niicount = 0
    for niistr in args.dwi_niigzs:
        niicount = niicount + 1
        nii = Path(niistr).resolve()
        base = nii.name[:-7]
        dir_token = "fwd"
        acq_token = f"{niicount:02d}"
        for ext in [".nii.gz", ".bval", ".bvec", ".json"]:
            src = nii.parent / (base + ext)
            dst = sess_root / "dwi" / strict_dwi_bids_name(subj, sess, acq_token, dir_token, ext)
            if src.exists():
                copy_file(src, dst)
                if ext == ".json": update_dwi_json(dst, reverse_pedir=False)
            else:
                raise Exception(f"Source file not found for {src}")

    # RPE
    niistr = args.rpe_niigz
    niicount = niicount + 1
    nii = Path(niistr).resolve()
    base = nii.name[:-7]
    dir_token = "rev"
    acq_token = f"{niicount:02d}"
    for ext in [".nii.gz", ".bval", ".bvec", ".json"]:
        src = nii.parent / (base + ext)
        dst = sess_root / "dwi" / strict_dwi_bids_name(subj, sess, acq_token, dir_token, ext)
        if src.exists():
            copy_file(src, dst)
            if ext == ".json": update_dwi_json(dst, reverse_pedir=True)
        else:
            raise Exception(f"Source file not found for {src}")

    # T1w
    nii = Path(args.t1_niigz).resolve()
    base = nii.name[:-7]
    for ext in [".nii.gz", ".json"]:
        src = nii.parent / (base + ext)
        dst = sess_root / "anat" / strict_t1w_bids_name(subj, sess, ext)
        if src.exists():
            copy_file(src, dst)
        else:
            raise Exception(f"Source file not found for {src}")
    
    # Dataset-level files
    save_json(bids_root / "dataset_description.json", {"Name":"BIDS dataset","BIDSVersion":"1.9.0","DatasetType":"raw"})
    part_tsv = bids_root / "participants.tsv"
    if part_tsv.exists():
        old = set(x.strip() for x in part_tsv.read_text().splitlines()[1:] if x.strip())
        old.add(subj)
        rows = sorted(old)
    else:
        rows = [subj]
    with part_tsv.open("w") as f:
        f.write("participant_id\n")
        [f.write(f"{r}\n") for r in rows]


# ------------- CLI -------------
def main():
    ap = argparse.ArgumentParser(description="BIDSify QSIPrep inputs from a SINGLE FLAT INPUTS directory (XNAT-style).")
    ap.add_argument("--dwi_niigzs", required=True, nargs='*', help="One or more DWI series, all same PE dir")
    ap.add_argument("--rpe_niigz", required=True, help="Reverse PE DWI series for TOPUP")
    ap.add_argument("--t1_niigz", required=True, help="T1 image")
    ap.add_argument("--out_dir", required=True, help="OUTPUTS dir (all artifacts go here)")
    ap.add_argument("--subject_label", required=True, help="Original XNAT subject label (will be sanitized for BIDS)")
    ap.add_argument("--session_label", required=True, help="Original XNAT session label (will be sanitized for BIDS)")
    args = ap.parse_args()
    bidsify(args)


if __name__ == "__main__":
    main()
