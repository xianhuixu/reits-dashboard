#!/bin/bash
# 同步站点到 Cloudflare Pages（国内访问更快的镜像）
# 用法：bash deploy_cf.sh   （在仓库根目录执行）
set -e
cd "$(dirname "$0")"
rm -rf .cf-deploy
mkdir .cf-deploy
cp index.html app.js styles.css ui-utils.js _headers .cf-deploy/
cp data.json data_research.json news.json corp_actions.json projects.json reits_snapshot.json .cf-deploy/
cp 6015e57c6c228145fd65bb64b909526d.txt .cf-deploy/
cp -r lib icons .cf-deploy/
npx wrangler pages deploy .cf-deploy --project-name=reits-dashboard --branch=main --commit-dirty=true
