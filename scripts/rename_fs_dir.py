#!/usr/bin/env python3

import argparse
import re
import shutil
from pathlib import Path

def sanitize_bids_label(raw_label: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9]+', '', raw_label)
    return cleaned or "UNKNOWN"

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fs_dir", required=True)
    ap.add_argument("--subject_label", required=True)
    ap.add_argument("--session_label", required=True)
    ap.add_argument("--subjects_dir", required=True)
    args = ap.parse_args()

    subj_clean = sanitize_bids_label(args.subject_label)
    sess_clean = sanitize_bids_label(args.session_label)
    subj = f"sub-{subj_clean}"
    sess = f"ses-{sess_clean}"
    fs_root = Path(args.subjects_dir).resolve()
    sess_root = fs_root / subj / sess
    ensure_dir(sess_root)
    shutil.copytree(Path(args.fs_dir).resolve(), sess_root)

if __name__ == "__main__":
    main()
