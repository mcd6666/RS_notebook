#!/bin/bash
#SBATCH --job-name=dino-router_ddp
#SBATCH --partition=bigtrain
#SBATCH --gres=gpu:rtx_pro_6000:2
#SBATCH --cpus-per-task=16
#SBATCH --mem=160G
#SBATCH --time=72:00:00
#SBATCH --output=/data/logs/%u/%x-%j.out
#SBATCH --error=/data/logs/%u/%x-%j.err

set -euo pipefail

export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8
export OMP_NUM_THREADS=8

echo "========== Slurm Info =========="
echo "Job ID: ${SLURM_JOB_ID:-}"
echo "Job Name: ${SLURM_JOB_NAME:-}"
echo "User: ${USER:-}"
echo "Node: ${SLURMD_NODENAME:-}"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}"
echo "================================"

nvidia-smi || true

echo "========== Conda Info =========="
set +u
source /data/users/mcd/project/env/dinounet/bin/activate
set -u

which python
python -V
echo "CONDA_PREFIX=${CONDA_PREFIX:-not_set}"
echo "Conda env: ${CONDA_DEFAULT_ENV:-not_activated}"
echo "================================"

export CKPT_DIR=/data/checkpoints/${USER}/${SLURM_JOB_NAME}/${SLURM_JOB_ID}
export OUTPUT_DIR="$CKPT_DIR/outputs"
export TB_DIR="$OUTPUT_DIR/tensorboard"
mkdir -p "$CKPT_DIR" "$OUTPUT_DIR" "$TB_DIR"

cd /data/users/mcd/project/dino_router

echo "========== Start DDP Training =========="
echo "Checkpoint dir: $CKPT_DIR"
echo "Output dir: $OUTPUT_DIR"
echo "TensorBoard dir: $TB_DIR"
echo "Workdir: $(pwd)"
echo "========================================"

torchrun --standalone --nproc_per_node=2 /data/users/mcd/project/dino_router/train_query_moe_v2_advanced.py \
  --mode three_stage \
  --image_size 256 \
  --batch_size 4 \
  --accumulation_steps 2 \
  --num_workers 8 \
  --pin_memory \
  --persistent_workers \
  --strong_aug \
  --stage1_epochs 40 \
  --stage2_epochs 85 \
  --stage3_epochs 30 \
  --boundary_loss \
  --tensorboard \
  --no-lora_full_freeze \
  --tensorboard_log_dir "$TB_DIR" \
  --tensorboard_run_name "${SLURM_JOB_NAME}-${SLURM_JOB_ID}" \
  --seed 3407 \
  --patience 25
