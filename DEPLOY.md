# 部署指南

项目已打包为 `deploy-package.zip`，包含以下文件：
- `index.html` — 主应用
- `manifest.json` — PWA 配置
- `sw.js` — 离线缓存服务
- `icon-*.png` — 应用图标

---

## 方案一：Netlify Drop（推荐，30秒搞定）

**优点**：无需注册账号，直接拖拽部署，自动生成 HTTPS 域名，支持 PWA

1. 在电脑浏览器打开：https://app.netlify.com/drop
2. 把当前文件夹（或解压后的 deploy-package 文件夹）**拖拽**到网页中间的区域
3. 等待几秒钟，会自动部署完成
4. 获得一个类似 `https://xxx-xxx-xxx.netlify.app` 的网址
5. 用 iPhone Safari 打开这个网址 → 分享 → 添加到主屏幕

---

## 方案二：GitHub Pages（免费、稳定）

**优点**：免费，自定义域名方便，长期稳定

1. 在 GitHub 创建一个新仓库（如 `my-workbench`）
2. 把当前文件夹内所有文件上传到仓库
3. 进入仓库 Settings → Pages
4. Source 选择 Deploy from a branch → Branch 选 main → Folder 选 /root → Save
5. 等待 1-2 分钟，访问 `https://你的用户名.github.io/my-workbench/`

---

## 方案三：Cloudflare Pages（免费、速度快）

**优点**：全球 CDN，国内访问速度好

1. 注册 Cloudflare 账号（免费）
2. 进入 Cloudflare Dashboard → Pages
3. 点击 Create a project → Upload assets
4. 把当前文件夹压缩为 zip 上传
5. 获得部署地址

---

## iPhone 添加到主屏幕

无论用哪种方案部署后：

1. iPhone Safari 打开部署后的网址
2. 点击底部分享按钮（方框带向上的箭头）
3. 找到「添加到主屏幕」→ 添加
4. 桌面会出现「记账工作台」图标，点击即可像 App 一样使用

---

## 注意事项

- 所有数据存储在浏览器本地，换设备或清除浏览器数据会丢失
- 建议定期在「设置」页面导出 JSON 备份
- 首次加载后支持离线使用
