#!/usr/bin/env bash
# CD v1 远端部署脚本（ci-cd-plan §4）——runner 侧调用，全部值经 Secrets/Vars 注入。
# 红线：只碰 api/admin 具名服务；永不裸 up / --remove-orphans / 平台层 / prune -a / --volumes。
set -euo pipefail

# 多行 PEM 须落临时文件（内联 -i 会把后续行当参数）
KEY_FILE=$(mktemp); printf '%s\n' "$VPS_SSH_KEY" > "$KEY_FILE"; chmod 600 "$KEY_FILE"
trap 'rm -f "$KEY_FILE"' EXIT
SSH="ssh -i $KEY_FILE -p $VPS_PORT -o StrictHostKeyChecking=accept-new $VPS_USER@$VPS_HOST"
SCP="scp -i $KEY_FILE -P $VPS_PORT -o StrictHostKeyChecking=accept-new"

echo "[deploy] 1/8 preflight（内存/磁盘守卫＋cron 窗口告警）"
PREFLIGHT_B64=$(base64 -w0 <<'REMOTE'
FREE_MB=$(free -m | awk '/^Mem:/{print $7}')
DISK_PCT=$(df / | awk 'NR==2{gsub("%","",$5);print $5}')
if [ "$DISK_PCT" -gt 90 ]; then
  docker builder prune --filter until=24h -f >/dev/null 2>&1 || true
  DISK_PCT=$(df / | awk 'NR==2{gsub("%","",$5);print $5}')
fi
[ "$DISK_PCT" -gt 90 ] && echo "磁盘 ${DISK_PCT}% 超守卫，中止" && exit 1
[ "$FREE_MB" -lt 300 ] && echo "可用内存 ${FREE_MB}MB 不足，中止" && exit 1
echo "守卫过：磁盘 ${DISK_PCT}% / 可用内存 ${FREE_MB}MB"
REMOTE
)
$SSH "echo $PREFLIGHT_B64 | base64 -d | bash"

NOW_UTC=$(date -u +%H:%M)
for WIN in $CRON_WINDOWS; do
  W_S=$(echo "$WIN" | cut -d- -f1); W_E=$(echo "$WIN" | cut -d- -f2)
  if [[ "$NOW_UTC" > "$W_S" && "$NOW_UTC" < "$W_E" ]]; then
    echo "::warning::命中 cron 窗口 $WIN（仅提醒不阻断）"
  fi
done

echo "[deploy] 2/8 留旧包（回滚兜底）"
$SSH 'cp ~/deploy.tgz ~/rollback.tgz 2>/dev/null || echo "（首次部署无旧包）"'

echo "[deploy] 3/8 上传新包＋解包"
$SCP /tmp/deploy.tgz "$VPS_USER@$VPS_HOST:~/deploy.tgz"
$SSH "sudo -n tar xzf ~/deploy.tgz -C $DEPLOY_PATH --overwrite && sudo -n find $DEPLOY_PATH -name '._*' -delete && echo 解包OK"

echo "[deploy] 4/8 重建面判定（marker——变化即双面重建，保守不漏建）"
MARKER=$($SSH "cat $DEPLOY_PATH/deploy.marker 2>/dev/null || echo none")
if [ "$MARKER" = "$SHA" ]; then R_API=0; R_ADMIN=0; else R_API=1; R_ADMIN=1; fi
echo "  判定：api=$R_API admin=$R_ADMIN（marker=$MARKER -> $SHA）"

if [ "$DRY_RUN" = "true" ]; then
  echo "[deploy] DRY_RUN 到此为止（会重建 api=$R_API admin=$R_ADMIN）——不碰容器"
  exit 0
fi

echo "[deploy] 5/8 构建切换（build-arg 带 GIT_SHA；marker 变化即双面重建——保守不漏建）"
if [ "$R_API" = "1" ]; then
  # F2：build 前给当前运行镜像打 :prev——保留一版镜像，回滚恢复秒级加速选项
  $SSH "sudo -n docker tag what-to-eat/api:dev what-to-eat/api:prev 2>/dev/null; sudo -n docker tag what-to-eat/admin:dev what-to-eat/admin:prev 2>/dev/null; true"
  $SSH "cd $DEPLOY_PATH && sudo -n docker compose build --build-arg GIT_SHA=$SHA api admin && sudo -n docker compose up -d api admin"
  sleep 14
else
  echo "  同 SHA 已部署——跳过重建"
fi

echo "[deploy] 6/8 health 分层断言（6 次×10s）"
$SSH "API_OK=0
for i in 1 2 3 4 5 6; do
  V=\$(curl -s http://127.0.0.1:8881/api/health | grep -o '\"version\":\"[^\"]*\"' || true)
  echo \"  api try\$i: \$V\"
  echo \"\$V\" | grep -q '$SHA' && API_OK=1 && break
  sleep 10
done
[ \"\$API_OK\" = 1 ] || { echo 'FAIL: api 回环 health 未含新 SHA'; exit 1; }
curl -s http://127.0.0.1:8001/api/health >/dev/null && echo '  admin 回环 OK' || { echo 'FAIL: admin health'; exit 1; }"

if [ "$SKIP_PUB" != "true" ]; then
  echo "  公网层：$WTE_DOMAIN"
  CODE=000
  for i in 1 2 3 4 5 6; do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://$WTE_DOMAIN/api/health" || echo 000)
    [ "$CODE" = "200" ] && break; sleep 10
  done
  [ "$CODE" = "200" ] || { echo "FAIL: 公网 health $CODE"; exit 1; }
  AC=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://$WTE_DOMAIN/api/admin/x" || echo 000)
  { [ "$AC" = "403" ] || [ "$AC" = "404" ]; } || { echo "FAIL: 公网 admin 未拦（$AC）"; exit 1; }
  echo "  公网层 OK（health 200＋admin $AC）"
else
  echo "  ::warning::备案降级期——公网断言跳过（降级版本区间记私有注记）"
fi

echo "[deploy] 7/8 写 marker（断言全过后才写）"
$SSH "echo $SHA | sudo -n tee $DEPLOY_PATH/deploy.marker >/dev/null && echo marker=$SHA"

echo "[deploy] 8/8 收尾（仅 dangling prune；绝不 -a / --volumes）"
$SSH "sudo -n docker image prune -f >/dev/null 2>&1 || true; df -h / | tail -1"
echo "== deploy 成功 =="
