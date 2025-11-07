## Getting Data Into BIDS Format

To use the **QSIPrep** pipeline, your data must first be organized in **BIDS format**.

---

### 1️⃣ T1-weighted 

Download the T1-weighted files from XNAT:

```
scans -> 201-cs_T1W_3D_TFE_32_channel -> resources -> nifti + json
```

Place this file in:

```
INPUTS/
```

---

### 2️⃣ DWI Runs (b2000 AP, b1000 AP)

Download the two DWI runs (b1000 AP, b2000 AP) from XNAT:

```
scans -> bX000app_fov140 -> nifti + json + bval + bvec
```

Then place each in the INPUTS/:

Download the b1000 PA from XNAT:

```
scans -> bX000apa_fov140 -> nifti + json + bval + bvec
```

Then place in the INPUTS/

---

### 3️⃣ FreeSurfer Data

1. Download the FreeSurfer data for your participant from XNAT.
2. Copy folder the named SUBJECT
3. Place SUBJECT folder in INPUTS/ 


You should now have all required **XNAT files**. Proceed to **BIDSify your data** and run **QSIPrep**:

```bash
docker run --rm -it \                 
  --platform linux/amd64 \
  -v "${INPUTS}":/inputs:ro \
  -v "${OUTPUTS}":/outputs \
  -v "${FS_LICENSE}":/opt/freesurfer/license.txt:ro \
  -v "$(dirname "${BIDSIFY}")":/scripts:ro \
  --entrypoint /bin/bash \
  pennlinc/qsiprep:1.0.1 \
  -lc 'set -euxo pipefail; \
       python /scripts/'"$(basename "${BIDSIFY}")"' \
         --inputs-dir /inputs \
         --outputs-dir /outputs \
         --subject '"${SUBJ}"' && \
       qsiprep /outputs/BIDS /outputs/derivatives participant \
         --stop-on-first-crash \
         --output-resolution 2 \
         --nprocs 12 \
         --write-graph \
         --omp-nthreads 12 \
         --mem 32000 \
         -w /outputs/work \
         --fs-license-file /opt/freesurfer/license.txt'
```

After bidsify_qsiprep.py, your BIDS folder should contain three subdirectories: `dwi`, `anat`, `fmap`.

🕒 Expected runtime for entire qsiprep container: ~16 hours locally (per participant).

Output (under `derivatives/`):
- Preprocessed **DWI** and **anat** files
- **Figures** (e.g., denoising)
- **Transform files** for MNI conversion
- **Logs** describing the pipeline steps

### 4️⃣ Running QSIRecon


For our purposes, we will be using a custom atlas. This will require the custom atlas to be built and injected into the QSIRecon workflow, similar to what we are doing in the xcp-d processor. The working directory will need a folder that looks like this:

Required structure:
```
atlas-name/
├── atlas-name_dseg.tsv
├── atlas-name_space-MNI152NLin2009cAsym_dseg.json
└── atlas-name_space-MNI152NLin2009cAsym_res-0[insert num]_dseg.nii.gz
```

Per Baxter, this can be done by referencing relevant commits from https://github.com/VUIIS/xcpd-processors/tree/main. We will be using `atlas-MMPthalTian` https://github.com/VUIIS/xcpd-processors/tree/main/atlases/atlas-MMPthalTian



Run the following code to accomplish this and run QSIRecon with a custom atlas (where custom_atlas refers to the relevant commit in xcp-d). `SPEC_DIR` = the yaml file in the `qsirecon_specs` folder. You can make edits to the MRtrix commands QSIRecon performs here.

```bash
docker run --rm --platform linux/amd64 \
  -v "${DERIV}":/in:ro \
  -v "${OUT}":/out \
  -v "${WORK}":/work \
  -v "${ATLAS_ROOT}":/custom_atlas:ro \
  -v "${FS_DIR}":/fsdir:ro \
  -v "${FS_LICENSE}":/opt/freesurfer/license.txt:ro \
  -v "${SPEC_DIR}":/specs:ro \
  -v "$(dirname "${custom_atlas}")":/scripts:ro \
  --entrypoint /bin/bash \
  pennlinc/qsirecon:1.0.1 \
  -lc "set -euxo pipefail; \
    python /scripts/$(basename "${custom_atlas}") /custom_atlas; \
    qsirecon /in /out participant \
      --input-type qsiprep \
      --recon-spec /specs/mrtrix_hsvs.yaml \
      --fs-subjects-dir /fsdir \
      --fs-license-file /opt/freesurfer/license.txt \
      --datasets /custom_atlas \
      --atlases MMPthalTian \
      --output-resolution 2.0 \
      --nprocs 12 \
      --omp-nthreads 12 \
      --mem 32000 \
      -w /work \
      --stop-on-first-crash \
      -v -v"
```
---

If you are using a built-in QSIRecon atlas (e.g., 4S, Brainnetome) run the following code:

```bash
docker run --rm --platform linux/amd64 \
  -v "${DERIV}":/in:ro \
  -v "${OUT}":/out \
  -v "${WORK}":/work \
  -v "${FS_DIR}":/fsdir:ro \
  -v "${FS_LICENSE}":/opt/freesurfer/license.txt:ro \
  -v "${SPEC_DIR}":/specs:ro \
  --entrypoint /bin/bash \
  pennlinc/qsirecon:1.0.1 \
    /in /out participant \
    --input-type qsiprep \
    --recon-spec /specs/mrtrix_hsvs.yaml \
    --fs-subjects-dir /fsdir \
    --fs-license-file /opt/freesurfer/license.txt \
    --atlases 4S156Parcels \
    --output-resolution 2.0 \
    --nprocs 12 \
    --omp-nthreads 12 \
    --mem 32000 \
    -w /work \
    --stop-on-first-crash \
    -v -v
```