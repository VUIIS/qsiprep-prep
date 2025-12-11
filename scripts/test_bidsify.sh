#!/usr/bin/env bash

export PATH=$(pwd):$PATH

bidsify_qsiprep_func.py \
    --dwi_niigzs $(pwd)/../INPUTS/scans/801_dti_2min_b1000app_fov140.nii.gz $(pwd)/../INPUTS/scans/1001_dti_2min_b2000app_fov140.nii.gz \
    --rpe_niigz $(pwd)/../INPUTS/scans/901_dti_2min_b1000apa_fov140.nii.gz \
    --t1_niigz $(pwd)/../INPUTS/scans/201_cs_T1W_3D_TFE_32_channel.nii.gz \
    --fs_dir $(pwd)/../INPUTS/freesurfer741_v2/SUBJECT \
    --out_dir $(pwd)/../OUTPUTS \
    --subject_label 257032 \
    --session_label 257032

