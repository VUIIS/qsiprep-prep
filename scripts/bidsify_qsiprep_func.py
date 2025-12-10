#!/usr/bin/env python3

# FIXME Do not use fmap approach - all dwi in dwi BIDS dir, with suitable PhaseEncodingDirection

# BPR FIXME
# Take inputs as
#  --dwi_niigz /path/to/dwi1.nii.gz /path/to/dwi2.nii.gz  [with variable number]
#  --rpe_niigz /path/to/rpe.nii.gz
#  --t1_niigz /path/to/t1.nii.gz
#  --fs_dir  /path/to/SUBJECT
#
# Then generate bval/bvec/json filenames from stems of the above.
#
# Can we get rid of infer_primary_bval_from_bvalfile, i.e. no assumption about bvals? Main 
# concern here is that two different DWI series might have the same most common bval,
# resulting in different dwi series with the same bids filename. E.g. for acq tag, can we 
# instead use 01, 02, ... based on ordering in the argument list?
#
# Regarding dir tag in dwi filename: "The use of generic labels, such as dir-reference and 
# dir-reversed, is RECOMMENDED to avoid any possible inconsistency." I'd suggest dir-fwd
# and dir-rev
#
# Are we sure epi is the correct type for the fmap rpe, rather than dwi? Does qsiprep correctly
# find b-0 images in this case?
#
# Shall we require primary pedir as an input instead of trying to guess? Along with assuming
# DWI/RPE are opposite dir but all the same axis.
#
# Ideally don't look at filenames at all.


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

def strict_dwi_bids_name(subj,acq_token,dir_token,suffix):
    return f"{subj}_acq-{acq_token}_dir-{dir_token}_dwi{suffix}"

def strict_t1w_bids_name(subj,suffix):
    return f"{subj}_T1w{suffix}"


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
    
    # FIXME Add session to paths and filenames
    subj_clean = sanitize_bids_subj(args.subject_label)
    subj = f"sub-{subj_clean}"
    bids_root = Path(args.out_dir).resolve() / "BIDS"
    subj_root = bids_root / subj
    for d in (subj_root/"dwi", subj_root/"anat"): ensure_dir(d)

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
            dst = subj_root / "dwi" / strict_dwi_bids_name(subj, acq_token, dir_token, ext)
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
        dst = subj_root / "dwi" / strict_dwi_bids_name(subj, acq_token, dir_token, ext)
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
        dst = subj_root / "anat" / strict_t1w_bids_name(subj, ext)
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

    # Subject map
    #map_path = bids_root / "bids_subject_map.tsv"
    #if map_path.exists():
    #    lines = [ln.strip().split("\t") for ln in map_path.read_text().splitlines() if ln.strip()]
    #    header = lines[0] if lines else ["xnat_subject","bids_subject"]
    #    existing = {tuple(row) for row in lines[1:]} if len(lines)>1 else set()
    #    existing.add((subj_raw, subj)); pairs = sorted(existing)
    #else:
    #    header = ["xnat_subject","bids_subject"]; pairs = [(args.subject_label, subj)]
    #with map_path.open("w") as f:
    #    f.write("\t".join(header) + "\n")
    #    for a,b in pairs: f.write(f"{a}\t{b}\n")


# ------------- CLI -------------
def main():
    ap = argparse.ArgumentParser(description="BIDSify QSIPrep inputs from a SINGLE FLAT INPUTS directory (XNAT-style).")
    ap.add_argument("--dwi_niigzs", required=True, nargs='*', help="One or more DWI series, all same PE dir")
    ap.add_argument("--rpe_niigz", required=True, help="Reverse PE DWI series for TOPUP")
    ap.add_argument("--t1_niigz", required=True, help="T1 image")
    ap.add_argument("--fs_dir", required=True, help="Freesurfer subject directory")
    ap.add_argument("--out_dir", required=True, help="OUTPUTS dir (all artifacts go here)")
    ap.add_argument("--subject_label", required=True, help="Original XNAT subject label (will be sanitized for BIDS)")
    ap.add_argument("--session_label", required=True, help="Original XNAT session label (will be sanitized for BIDS)")
    args = ap.parse_args()
    bidsify(args)


if __name__ == "__main__":
    main()
