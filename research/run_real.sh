#!/bin/bash
cd "C:/Users/HP/.t3/projects/fp-2/research"
export CRYNET_FAST=0
export CRYNET_OFFLINE=1
export CRYNET_KINDS=conv_cnn,sep_cnn
export CRYNET_EPOCHS=4
export CRYNET_CACHE="C:/Users/HP/.t3/projects/fp-2/research/_cache"
export CRYNET_WORK="C:/Users/HP/.t3/projects/fp-2/research/_real_work"
export CRYNET_OUT="C:/Users/HP/.t3/projects/fp-2/research/_real_out"
export PYTHONIOENCODING=utf-8
python run_notebook_local.py
