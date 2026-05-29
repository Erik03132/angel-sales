#!/bin/bash
# ==============================================================
# SYNC TO SYNLOGY NAS DS720 – Heavy files backup & folder cleanup
# --------------------------------------------------------------
# Requirements on the NAS:
#   * SSH service enabled (preferred) OR SMB share with write access
#   * A dedicated user with a strong password (see .env variables below)
#   * Optional: enable Rsync daemon (default port 873) for faster sync
# --------------------------------------------------------------
# This script can be run manually or scheduled via cron (e.g. nightly).
# It performs:
#   1) Mount the NAS share (if using SMB) to a local mount point.
#   2) Rsync selected local directories to the NAS, preserving
#      hierarchy, timestamps, and handling large files efficiently.
#   3) Clean up empty source subfolders after successful transfer
#      (optional – controlled by CLEANUP_AFTER_SYNC flag).
# --------------------------------------------------------------
# Environment variables (add to ~/.env):
#   NAS_IP            – IP address of the Synology NAS (e.g. 192.168.1.25)
#   NAS_USER          – User with write permissions on the NAS
#   NAS_PASS          – Password for NAS_USER
#   NAS_SHARE         – Name of the SMB share (e.g. "backup")
#   NAS_MOUNT_POINT   – Local directory to mount the share (e.g. /mnt/nas)
#   SYNC_SRC_DIRS     – Space‑separated list of local dirs to sync
#   CLEANUP_AFTER_SYNC – "yes" to delete source files after successful sync
# --------------------------------------------------------------
# Example .env additions (fill in your own values):
#   NAS_IP=192.168.1.25
#   NAS_USER=igor
#   NAS_PASS=SuperSecretPass123
#   NAS_SHARE=backup
#   NAS_MOUNT_POINT=/mnt/nas
#   SYNC_SRC_DIRS="/Users/igorvasin/freelance-2026/data/heavy /Users/igorvasin/freelance-2026/ai-eggs/data/bigfiles"
#   CLEANUP_AFTER_SYNC=yes
# --------------------------------------------------------------

set -euo pipefail

# Load .env (if present)
ENV_FILE="$(dirname "$(dirname "$(realpath "$0")")")/.env"
if [[ -f "$ENV_FILE" ]]; then
  export $(grep -v '^#' "$ENV_FILE" | xargs)
fi

# Validate required variables
required_vars=(NAS_IP NAS_USER NAS_PASS NAS_SHARE NAS_MOUNT_POINT SYNC_SRC_DIRS)
for var in "${required_vars[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    echo "[ERROR] Missing required env var: $var"
    exit 1
  fi
done

# -------------------------------------------------------------
# 1️⃣ Mount SMB share (if not already mounted)
# -------------------------------------------------------------
if ! mountpoint -q "$NAS_MOUNT_POINT"; then
  echo "[INFO] Mounting SMB share //${NAS_IP}/${NAS_SHARE} to $NAS_MOUNT_POINT"
  sudo mkdir -p "$NAS_MOUNT_POINT"
  sudo mount -t cifs "//${NAS_IP}/${NAS_SHARE}" "$NAS_MOUNT_POINT" \
    -o username=$NAS_USER,password=$NAS_PASS,vers=3.0,iocharset=utf8,rw
else
  echo "[INFO] Share already mounted at $NAS_MOUNT_POINT"
fi

# -------------------------------------------------------------
# 2️⃣ Rsync each source directory to the NAS
# -------------------------------------------------------------
for src in $SYNC_SRC_DIRS; do
  if [[ -d "$src" ]]; then
    # Preserve relative path inside the mount point
    rel_path=$(realpath --relative-to "$HOME" "$src")
    dst="$NAS_MOUNT_POINT/$rel_path"
    echo "[INFO] Syncing $src → $dst"
    mkdir -p "$dst"
    rsync -avh --progress "$src/" "$dst/"
  else
    echo "[WARN] Source directory does not exist: $src"
  fi
done

# -------------------------------------------------------------
# 3️⃣ Optional cleanup – delete source files after successful sync
# -------------------------------------------------------------
if [[ "${CLEANUP_AFTER_SYNC:-no}" == "yes" ]]; then
  echo "[INFO] Cleaning up source directories..."
  for src in $SYNC_SRC_DIRS; do
    if [[ -d "$src" ]]; then
      # Remove empty directories, keep structure for future use
      find "$src" -type f -delete
      find "$src" -type d -empty -delete
    fi
  done
  echo "[INFO] Cleanup complete."
else
  echo "[INFO] Cleanup after sync is disabled (CLEANUP_AFTER_SYNC != yes)."
fi

# -------------------------------------------------------------
# 4️⃣ Unmount (optional – you may keep it mounted for later use)
# -------------------------------------------------------------
# sudo umount "$NAS_MOUNT_POINT"

echo "[DONE] Sync to NAS completed successfully."
