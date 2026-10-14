#!/usr/bin/env bash
# 给 opencli 自己打开的标签页续租：每 15 秒对会话发一次只读 eval。
# opencli 的会话租约 TTL 约 45 秒，空闲（等人登录、放行权限、填账号）时标签页会被回收，
# 未保存的表单整页丢失。等人操作期间在后台跑它，人操作完就停。
#
#   scripts/opencli_keepalive.sh <session> [minutes=30]
set -u
SESSION="${1:?usage: opencli_keepalive.sh <session> [minutes]}"
MINUTES="${2:-30}"
OC="${OPENCLI_BIN:-$(command -v opencli || echo "$HOME/.npm-global/bin/opencli")}"
END=$(( $(date +%s) + MINUTES * 60 ))
while [ "$(date +%s)" -lt "$END" ]; do
  "$OC" browser "$SESSION" eval 'document.title' >/dev/null 2>&1
  sleep 15
done
