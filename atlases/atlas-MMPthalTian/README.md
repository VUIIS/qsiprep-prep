# atlas-MMPthalTian custom atlas for qsirecon

This is copied from https://github.com/VUIIS/xcpd-processors/tree/main/atlases/atlas-MMPthalTian

Do not edit it here, as that will get the two sources out of sync.

The two versions of the atlas here (MNI152NLin6Asym, MNI152NLin2009cAsym) are identical, so 
the difference between these spaces is disregarded for this atlas.


To get the 1mm version:

    mri_convert \
        --like ${FSLDIR}/data/standard/MNI152_T1_1mm.nii.gz \
        -rt nearest \
        -i atlas-MMPthalTian_space-MNI152NLin2009cAsym_res-02_dseg.nii.gz \
        -o atlas-MMPthalTian_space-MNI152NLin2009cAsym_res-01_dseg.nii.gz

