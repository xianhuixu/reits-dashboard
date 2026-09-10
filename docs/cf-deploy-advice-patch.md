# Cloudflare 部署需补拷 advice.json

`daily-update.yml` 里「同步部署到 Cloudflare Pages」步骤当前 OAuth 无 `workflow` 权限，需仓库管理员手动改：

在 `cp data.json data_research.json ...` 一行加入 `advice.json`，并增加：

```bash
cp advice.js news.js corp_actions.js projects.js .cf-deploy/ 2>/dev/null || true
```

`deploy_cf.sh` 已在本 PR 修好。临时方案：`app.js` 会在本地 `advice.json` 失败时回退到
`https://xianhuixu.github.io/reits-dashboard/advice.json`。
