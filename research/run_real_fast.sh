#!/bin/bash
cd "C:/Users/HP/.t3/projects/fp-2/research"
export CRYNET_FAST=1
export CRYNET_OFFLINE=1
export CRYNET_CACHE="C:/Users/HP/.t3/projects/fp-2/research/_cache"
export CRYNET_WORK="C:/Users/HP/.t3/projects/fp-2/research/_realfast_work"
export CRYNET_OUT="C:/Users/HP/.t3/projects/fp-2/research/_realfast_out"
export PYTHONIOENCODING=utf-8
python run_notebook_local.py
