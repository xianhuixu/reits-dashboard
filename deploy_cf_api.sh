#!/bin/bash
# Cloudflare Pages Direct Upload API（绕过 wrangler，服务器内存小跑不动 node）
# 用法：CLOUDFLARE_API_TOKEN=xxx bash deploy_cf_api.sh
# 前提：已执行 bash deploy_cf.sh 的拷贝部分生成 .cf-deploy（本脚本不重新拷贝，直接用现成 .cf-deploy）
set -euo pipefail
cd "$(dirname "$0")"

TOKEN="${CLOUDFLARE_API_TOKEN:?请先设置环境变量 CLOUDFLARE_API_TOKEN}"
API="https://api.cloudflare.com/client/v4"

echo "==> 查询 Account ID"
ACCOUNTS=$(curl -s -H "Authorization: Bearer $TOKEN" "$API/accounts")
ACCOUNT_ID=$(echo "$ACCOUNTS" | python3 -c "
import json,sys
d=json.load(sys.stdin)
if not d.get('success'): print('ERR:'+json.dumps(d.get('errors'))); sys.exit(1)
accs=d['result']
print(accs[0]['id'])
")
echo "    account = $ACCOUNT_ID"

echo "==> 创建部署会话"
RESP=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$API/accounts/$ACCOUNT_ID/pages/projects/reits-dashboard/deployments" \
  -d '{"branch":"main"}')
echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print('    success:', d.get('success'))"
if echo "$RESP" | grep -q '"success":false'; then
  echo "创建部署失败：$RESP"; exit 1
fi

UPLOAD_URL=$(echo "$RESP" | python3 -c "
import json,sys
def find(o,key):
    if isinstance(o,dict):
        for k,v in o.items():
            if k==key: return v
            r=find(v,key)
            if r: return r
    elif isinstance(o,list):
        for v in o:
            r=find(v,key)
            if r: return r
print(find(json.load(sys.stdin),'upload_url') or '')
")
DEPLOY_ID=$(echo "$RESP" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(d.get('result',{}).get('id',''))
")
if [ -z "$UPLOAD_URL" ] || [ -z "$DEPLOY_ID" ]; then
  echo "!! 未找到 upload_url 或 deployment id，原始响应："
  echo "$RESP" | head -c 2000
  exit 1
fi
echo "    deployment = $DEPLOY_ID"

echo "==> 打包并上传 ($(du -sh .cf-deploy | cut -f1))"
tar -czf /tmp/cf-deploy.tar.gz -C .cf-deploy .
curl -s -X PUT -H "Content-Type: application/gzip" --data-binary "@/tmp/cf-deploy.tar.gz" "$UPLOAD_URL"
echo ""
echo "==> 标记部署完成"
FINAL=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$API/accounts/$ACCOUNT_ID/pages/projects/reits-dashboard/deployments" \
  -d "{\"branch\":\"main\",\"deployment_id\":\"$DEPLOY_ID\"}")
echo "$FINAL" | python3 -c "
import json,sys
d=json.load(sys.stdin)
r=d.get('result',{})
print('    success:', d.get('success'))
print('    url:', r.get('url'))
print('    environment:', r.get('environment'))
"
rm -f /tmp/cf-deploy.tar.gz
echo "==> 完成"