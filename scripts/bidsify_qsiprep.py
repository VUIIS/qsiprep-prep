#!/usr/bin/env python3

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

def strict_dwi_bids_name(subj,acq_token,dir_token,suffix):
    return f"{subj}_acq-{acq_token}_dir-{dir_token}_dwi{suffix}"
def strict_fmap_bids_name(subj,acq_token,dir_token,suffix):
    return f"{subj}_acq-{acq_token}_dir-{dir_token}_epi{suffix}"
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

def update_fmap_json(json_path: Path, reverse_pedir: Optional[bool], intended_files: list[str]):
    meta = load_json(json_path)
    if "EstimatedTotalReadoutTime" in meta:
        if not meta.get("TotalReadoutTime"):
            meta["TotalReadoutTime"] = meta["EstimatedTotalReadoutTime"]
        del meta["EstimatedTotalReadoutTime"]
    meta["IntendedFor"] = intended_files
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


# ------------- Stage from FLAT → OUTPUTS/INPUTS/... -------------
def stage_from_flat_inputs(
        dwi_niigzs: list,
        rpe_niigz: str,
        t1_niigz: str,
        fs_dir: str,
        outputs_dir: Path
        ) -> Tuple[Path,Path,Path,Optional[Path]]:

    dwi_out  = outputs_dir / "INPUTS" / "DWI"
    fmap_out = outputs_dir / "INPUTS" / "fmap"
    t1_out   = outputs_dir / "INPUTS" / "T1w"
    for d in (dwi_out,fmap_out,t1_out): ensure_dir(d)

    # DWI
    for nii in dwi_niigzs:
        rnii = Path(nii).resolve()
        dbase = rnii.parent
        fbase = rnii.name[:-7]
        for ext in [".nii.gz",".bval",".bvec",".json"]:
            src = dbase / (fbase + ext)
            if src.exists(): 
                copy_file(dbase / src, dwi_out / src.name)
            else:
                raise Exception(f'Missing input file {dbase / src}')

    # RPE/FMAP
    rnii = Path(rpe_niigz).resolve()
    dbase = rnii.parent
    fbase = rnii.name[:-7]
    for ext in [".nii.gz",".bval",".bvec",".json"]:
        src = dbase / (fbase + ext)
        if src.exists(): 
            copy_file(dbase / src, fmap_out / src.name)
        else:
            raise Exception(f'Missing input file {dbase / src}')

    # T1
    rnii = Path(t1_niigz).resolve()
    dbase = rnii.parent
    fbase = rnii.name[:-7]
    for ext in [".nii.gz",".json"]:
        src = dbase / (fbase + ext)
        if src.exists(): 
            copy_file(dbase / src, t1_out / f"t1{ext}")
        else:
            raise Exception(f'Missing input file {dbase / src}')

    # FreeSurfer SUBJECT or SUBJECT/SUBJECT
    fs_src = Path(fs_dir).resolve()
    fs_out = outputs_dir / "SUBJECT"
    shutil.copytree(fs_src, fs_out)

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
    niicount = 0
    for nii in sorted(dwi_in.glob("*.nii.gz")):
        niicount = niicount + 1
        base = nii.name[:-7]
        dir_token = "fwd"
        acq_token = f"{niicount:02d}"
        out_name = strict_dwi_bids_name(subj, acq_token, dir_token, ".nii.gz")
        copy_file(nii, subj_root / "dwi" / out_name)
        for ext in [".bval",".bvec",".json"]:
            src = dwi_in / (base + ext)
            dst = subj_root / "dwi" / strict_dwi_bids_name(subj, acq_token, dir_token, ext)
            if src.exists():
                copy_file(src, dst)
                if ext == ".json": update_dwi_json(dst, False)
            elif ext == ".json":
                raise Exception(f"Source json not found for {src}")
        intended_for.append(f"dwi/{out_name}")

    # FMAP → ALWAYS BIDS/fmap as *_epi.*
    # FIXME Something can't be right here, because we are not getting bvals which are needed
    # to correctly extract b=0 volumes for topup
    # niicount = 0  # Actually, don't reset this here so we don't get dup acq numbers btwn fwd/rev
    for fmap_nii in sorted(fmap_in.glob("*.nii.gz")):
        niicount = niicount + 1
        base = fmap_nii.name[:-7]
        dir_token = "rev"
        acq_token = f"{niicount:02d}"
        out_name = strict_fmap_bids_name(subj, acq_token, dir_token, ".nii.gz")
        copy_file(fmap_nii, subj_root / "fmap" / out_name)
        src_json = fmap_in / (base + ".json")
        dst_json = subj_root / "fmap" / strict_fmap_bids_name(subj, acq_token, dir_token, ".json")
        if src_json.exists():
            copy_file(src_json, dst_json)
            update_fmap_json(dst_json, True, intended_for)
        else:
            raise Exception(f"Source json not found for {src_json}")

    # T1w
    t1 = t1_in / "t1.nii.gz"
    if t1.exists():
        copy_file(t1, subj_root / "anat" / strict_t1w_bids_name(subj, ".nii.gz"))
    else:
        raise Exception(f"Source nii.gz not found for {src_json}")
    t1_json = t1_in / "t1.json"
    if t1_json.exists():
        copy_file(t1_json, subj_root / "anat" / strict_t1w_bids_name(subj, ".json"))
    else:
        raise Exception(f"Source json not found for {src_json}")    

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
    ap.add_argument("--dwi_niigzs", required=True, nargs='*', help="One or more DWI series, all same PE dir")
    ap.add_argument("--rpe_niigz", required=True, help="Reverse PE DWI series for TOPUP")
    ap.add_argument("--t1_niigz", required=True, help="T1 image")
    ap.add_argument("--fs_dir", required=True, help="Freesurfer subject directory")
    ap.add_argument("--outputs-dir", required=True, help="OUTPUTS dir (all artifacts go here)")
    ap.add_argument("--subject_label", required=True, help="Original XNAT subject label (will be sanitized for BIDS)")
    args = ap.parse_args()
    outputs_dir = Path(args.outputs_dir).resolve()
    stage_from_flat_inputs(args.dwi_niigzs, args.rpe_niigz, args.t1_niigz, args.fs_dir, outputs_dir)
    bidsify(outputs_dir, args.subject_label)

if __name__ == "__main__":
    main()
