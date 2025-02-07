#!/bin/bash

set -xe

[[ -n $GOOGLE_APPLICATION_CREDENTIALS ]] && gcloud auth activate-service-account --key-file $GOOGLE_APPLICATION_CREDENTIALS

RUN=gs://vcm-ml-code-testing-data/sample-prognostic-run-output-v4

random=$(openssl rand --hex 6)
tmpdir=/tmp/$random
OUTPUT=gs://vcm-ml-scratch/test-prognostic-report/$random

mkdir -p $tmpdir

# test shell
cd workflows/diagnostics
cat << EOF > $tmpdir/report.script
load $RUN
print
hovmoller PWAT
avg2d PWAT
map2d PWAT
eval $tmpdir/3d.script
jupyter
EOF

cat << EOF > $tmpdir/3d.script
meridional air_temperature
zonal air_temperature
zonalavg air_temperature
column air_temperature
avg3d air_temperature
EOF
prognostic_run_diags shell $tmpdir/report.script
# assert an image has been output
[[ -f image.png ]]
rm image.png  # cleanup

# compute diagnostics/mterics for a short sample prognostic run
prognostic_run_diags save $RUN $tmpdir/diags.nc --n-jobs=4
prognostic_run_diags metrics $tmpdir/diags.nc > $tmpdir/metrics.json
gsutil cp $tmpdir/diags.nc $OUTPUT/run1/diags.nc
gsutil cp $tmpdir/metrics.json $OUTPUT/run1/metrics.json

# generate movies for short sample prognostic run
prognostic_run_diags movie --n_jobs 1 --n_timesteps 2 $RUN $OUTPUT/run1

# generate report based on diagnostics computed above
prognostic_run_diags report $OUTPUT $OUTPUT

# cleanup
rm -r $tmpdir

echo "Yay! Prognostic run report integration test passed. You can view the generated report at:"
echo "https://storage.cloud.google.com/vcm-ml-scratch/test-prognostic-report/${random}/index.html"

