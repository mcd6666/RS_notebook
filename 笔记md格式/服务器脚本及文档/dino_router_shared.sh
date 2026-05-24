#!/bin/bash
#SBATCH --job-name=dino-router_train1
#SBATCH --partition=debug_shared
#SBATCH --gres=mps:40
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=48:00:00
#SBATCH --output=/data/logs/%u/%x-%j.out
#SBATCH --error=/data/logs/%u/%x-%j.err

set -euo pipefail

export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

echo "========== Slurm Info =========="
echo "Job ID: ${SLURM_JOB_ID:-}"
echo "Job Name: ${SLURM_JOB_NAME:-}"
echo "User: ${USER:-}"
echo "Node: ${SLURMD_NODENAME:-}"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}"
echo "================================"

# nvidia-smi ֻ�����ڲ鿴״̬����Ҫ����ʧ�ܵ���ѵ���˳�
nvidia-smi || true

echo "========== Conda Info =========="
# conda activate �ű��ڲ�����ʹ��δ�������������������ʱ�ر� set -u
set +u
source /data/users/mcd/project/env/dinounet/bin/activate
set -u

which python
python -V
echo "CONDA_PREFIX=${CONDA_PREFIX:-not_set}"
echo "Conda env: ${CONDA_DEFAULT_ENV:-not_activated}"
echo "================================"

echo "========== CUDA / PyTorch Check =========="
python - <<'PY'
import torch
print("torch:", torch.__version__)
print("torch cuda:", torch.version.cuda)
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("device:", torch.cuda.get_device_name(0))
    print("capability:", torch.cuda.get_device_capability(0))
    print("arch list:", torch.cuda.get_arch_list())
PY
echo "=========================================="

export CKPT_DIR=/data/checkpoints/${USER}/${SLURM_JOB_NAME}/${SLURM_JOB_ID}
export OUTPUT_DIR="$CKPT_DIR/outputs"
export TB_DIR="$OUTPUT_DIR/tensorboard"
mkdir -p "$CKPT_DIR" "$OUTPUT_DIR" "$TB_DIR"

cd /data/users/mcd/project/dino_router

echo "========== Start Training =========="
echo "Checkpoint dir: $CKPT_DIR"
echo "Output dir: $OUTPUT_DIR"
echo "TensorBoard dir: $TB_DIR"
echo "Workdir: $(pwd)"
echo "===================================="

python -u /data/users/mcd/project/dino_router/train_query_moe_v2_advanced.py \
  --mode three_stage \
  --image_size 256 \
  --strong_aug \
  --stage1_epochs 40 \
  --stage2_epochs 85 \
  --stage3_epochs 75 \
  --boundary_loss \
  --tensorboard \
  --no-lora_full_freeze \
  --tensorboard_log_dir "$TB_DIR" \
  --tensorboard_run_name "${SLURM_JOB_NAME}-${SLURM_JOB_ID}" \
  --seed 3407 \
  --patience 15
