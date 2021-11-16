#!/bin/bash

set -e
set -x

BASE_TAG="prognostic"
MODEL_BASE="gs://vcm-ml-experiments/2021-10-14-microphsyics-emulation-paper/models"
IMAGE="811d4a88b8b8f29d727f2d61f46f96b770c8ab47"

run_style=("offline" "online")
qc_tends=("all-tends-limited" "direct-qc-limited")
archictectures=("dense" "rnn")

for flag in ${run_style[@]}; do
    for tend in ${qc_tends[@]}; do
        for arch in ${archictectures[@]}; do
            TAG="${BASE_TAG}-${flag}-${tend}-${arch}-$(openssl rand -hex 4)"
            MODEL="${MODEL_BASE}/${tend}/${tend}-${arch}/model.tf"
            argo submit prog-run-and-eval.yaml \
                -p tag=$TAG \
		        -p image_tag=$IMAGE \
                -p baseline_tag="baseline" \
                -p config="$(< configs/default.yaml)" \
                -p tf_model=$MODEL \
                -p on_off_flag="--${flag}"
        done
    done
done