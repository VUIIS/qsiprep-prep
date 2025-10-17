## 🧠 Getting Data Into BIDS Format

To use the **QSIPrep** pipeline, your data must first be organized in **BIDS format**.

---

### 1️⃣ T1-weighted 

Download the T1-weighted files from XNAT:

```
scans -> 201-cs_T1W_3D_TFE_32_channel -> resources -> nifti + json
```

Place this file in:

```
INPUTS/T1w
```

---

### 2️⃣ DWI Runs (b2000 AP, b1000 AP)

Download the two DWI runs (b1000 AP, b2000 AP) from XNAT:

```
scans -> bX000app_fov140 -> nifti + json + bval + bvec
```

Then place each in the INPUTS/dwi folder:

Download the b1000 PA from XNAT:

```
scans -> bX000apa_fov140 -> nifti + json + bval + bvec
```

Then place each in the INPUTS/fmap folder

---

### 3️⃣ FreeSurfer Data

1. Download the FreeSurfer data for your participant from XNAT.
2. Rename the folder **“files”** to your participant’s ID in this format: `sub-ID`.
3. Move the renamed folder (and its subdirectories) into the `freesurfer` folder in this repo.
4. Replace the blank `license.txt` file in this repo with your actual **FreeSurfer license**.


You should now have all required **XNAT files**. Proceed to **BIDSify your data** and run **QSIPrep**:

```bash
docker run --rm -it \                           
  --platform linux/amd64 \
  -v "${INPUTS}":/inputs:ro \
  -v "${BIDS}":/bids \
  -v "${DERIV}":/out \
  -v "${WORK}":/work \
  -v "${FS_LICENSE}":/opt/freesurfer/license.txt:ro \
  -v "$(dirname "${BIDSIFY}")":/scripts:ro \
  --entrypoint /bin/bash \
  pennlinc/qsiprep:1.0.1 \
  -lc 'set -euxo pipefail; \
       python /scripts/'"$(basename "${BIDSIFY}")"' \
         --inputs-root /inputs \
         --bids-root /bids && \
       qsiprep /bids /out participant \
         --stop-on-first-crash \
         --output-resolution 2 \
         --nprocs 12 \
         --write-graph \
         --omp-nthreads 12 \
         --mem 32000 \
         -w /work \
         --fs-license-file /opt/freesurfer/license.txt'
```

In the above command you can either batch run all of your participants (no need to change anything) or add a `--sub` command to run just one participant

Where:
- `$SRC_ROOT` = path to your working directory  
- `$BIDS_ROOT` = path to your BIDS directory  
- `$BIDSIFY` = src/bidsify/bidsify_qsiprep.py

After bidsify_qsiprep.py, your BIDS folder should contain three subdirectories: `dwi`, `anat`, `fmap`.

🕒 Expected runtime for entire qsiprep container: ~16 hours locally (per participant).

Output (under `derivatives/`):
- Preprocessed **DWI** and **anat** files
- **Figures** (e.g., denoising)
- **Transform files** for MNI conversion
- **Logs** describing the pipeline steps