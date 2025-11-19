# GitLab CI/CD Pipeline Pending 问题排查指南

## 问题：Pipeline 一直处于 Pending 状态

### 可能的原因和解决方案

#### 1. **Runner 不可用或未配置**
   - **检查方法**：在 GitLab 项目页面 → Settings → CI/CD → Runners
   - **解决方案**：
     - 确保有可用的 Runner（共享 Runner 或项目专用 Runner）
     - 检查 Runner 状态是否为 "Online"
     - 如果没有 Runner，需要联系管理员配置

#### 2. **Tags 不匹配**
   - **问题**：配置中指定了 `tags: - docker`，但 Runner 没有这个 tag
   - **解决方案**：
     - 已移除 tags 限制，现在可以使用任何可用的 Runner
     - 或者查看 Runner 的 tags，然后匹配配置

#### 3. **Runner 类型不匹配**
   - **问题**：使用了 Docker executor，但 Runner 可能配置为其他类型
   - **解决方案**：
     - 检查 Runner 配置
     - 如果使用 Shell executor，需要修改配置

#### 4. **Docker-in-Docker 权限问题**
   - **问题**：需要 privileged 模式运行 Docker
   - **解决方案**：确保 Runner 配置允许 privileged 模式

## 关于 .env 文件

### ✅ 正确做法：不要提交 .env 文件
- `.env` 文件已在 `.gitignore` 中，不应该提交到 Git
- 这是正确的安全实践

### 🔧 在 CI/CD 中使用环境变量
在 GitLab 中配置 CI/CD 变量：
1. 进入项目 → Settings → CI/CD → Variables
2. 添加变量：
   - Key: `DEEPSEEK_API_KEY`
   - Value: 您的 DeepSeek API key
   - 勾选 "Mask variable"（隐藏变量值）
   - 勾选 "Protect variable"（仅在受保护分支使用）

### 📝 当前配置说明
- 代码中已使用 `os.getenv("DEEPSEEK_API_KEY")` 读取环境变量
- GitLab CI/CD 会自动将配置的变量注入到 pipeline 中
- 如果需要在构建时使用，可以在 `.gitlab-ci.yml` 中添加：

```yaml
variables:
  DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY}  # 从 CI/CD 变量读取
```

## 快速检查清单

- [ ] 检查 Runner 是否在线（Settings → CI/CD → Runners）
- [ ] 检查 Runner 是否有正确的权限（Docker executor）
- [ ] 移除或匹配 tags 配置
- [ ] 在 GitLab 中配置 `DEEPSEEK_API_KEY` 变量
- [ ] 检查 pipeline 日志中的错误信息

## 如果仍然无法运行

1. **查看 Pipeline 日志**：
   - 进入 CI/CD → Pipelines
   - 点击 pending 的 pipeline
   - 查看错误信息

2. **尝试简化配置**：
   - 可以先测试一个简单的 job，确认 Runner 可用

3. **联系管理员**：
   - 如果使用共享 Runner，可能需要联系 GitLab 管理员
   - 检查 Runner 的配置和权限

