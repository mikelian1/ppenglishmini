# 泡泡外刊 Mini（ppenglishmini）

泡泡外刊 Mini 是泡泡外刊的轻量运行版，面向只想直接使用阅读器的用户。

本仓库只需要包含：

```text
dist/
serve.py
run.bat
```

其中 `dist/` 是已经生成好的网页文件，`serve.py` 负责在本机提供网页和翻译接口，`run.bat` 用于 Windows 双击启动。

如果你想修改源码、调试页面、重新生成 `dist/`，请移步源码仓库：

[mikelian1/ppenglish](https://github.com/mikelian1/ppenglish)

## 功能简介

- 本地文章库：新建、打开、删除文章。
- 双语阅读：支持中英双栏、中英单栏、仅英文阅读模式。
- 整篇翻译：通过本机 `/api/translate` 接口调用 DeepSeek。
- 阅读样式：支持字号、行高、衬线/非衬线字体和多种主题。
- 查词：悬停英文单词，可打开有道和 Cambridge 词典链接。
- 高亮：荧光笔模式下拖选原文保存高亮。
- 生词本：手动添加、删除生词，也可在高亮后快速加入生词本。
- JSON 备份：导出/导入文章、译文、高亮和生词记录。

## 快速运行

在 Windows 上双击：

```text
run.bat
```

启动后访问：

```text
http://localhost:8000
```

`serve.py` 默认监听 `127.0.0.1:8000`，只面向本机浏览器使用，不主动开放给局域网或公网。

## 翻译配置

整篇翻译依赖 DeepSeek API Key。API Key 只应该保存在本机服务端侧，不要写进前端文件、截图或公开说明里。

首次双击 `run.bat` 时，如果系统还没有可用的 API Key，会提示输入 DeepSeek API Key。输入后会保存到 Windows Credential Manager 的通用凭据中。

凭据名称为：

```text
PPEnglish.DeepSeek.ApiKey
```

如果已经设置环境变量，`serve.py` 会优先读取：

```bash
DEEPSEEK_API_KEY=你的 DeepSeek API Key
```

可选环境变量：

```bash
DEEPSEEK_MODEL=deepseek-v4-flash
TRANSLATE_MAX_SOURCE_LENGTH=20000
TRANSLATE_MAX_BODY_BYTES=65536
DEEPSEEK_TIMEOUT=60
```

更换 API Key 时，可以打开 Windows“凭据管理器”，进入“Windows 凭据”，删除通用凭据 `PPEnglish.DeepSeek.ApiKey`，然后重新运行 `run.bat`。

## 使用流程

1. 打开首页“本地文章库”。
2. 点击“新建文章”。
3. 粘贴英文原文，必要时点击“清洗换行”。
4. 检查分段预览。
5. 点击“保存并阅读”。
6. 在阅读页点击“整篇翻译”。
7. 对不满意的段落使用“Google 重译”或“粘贴译文”手动修订。
8. 阅读时按需使用查词、高亮、生词本、主题、字号、行高和阅读模式。

## 本地数据与备份

文章、译文、高亮和生词都保存在当前浏览器的本地数据中，不会自动同步到云端。

注意事项：

- 清理站点数据、换浏览器、换端口或换域名，都可能导致看不到原文章。
- 首页“导出 JSON”可以导出文章和生词，适合备份或迁移到另一台电脑。
- 导入 JSON 时，如果遇到同 ID 文章或同名生词，会跳过重复项，不覆盖本地已有数据。

## 常见问题

### 双击 `run.bat` 后提示找不到 Python 怎么办？

说明当前 Windows 环境找不到 `python` 命令。请先安装 Python，并确认安装时勾选了加入 PATH，然后重新运行 `run.bat`。

### 为什么直接打开 `dist/` 里的文件不能翻译？

`dist/` 只是网页文件，整篇翻译还需要同源接口 `/api/translate`。请通过 `run.bat` 启动，让 `serve.py` 同时提供网页和翻译代理。

### 为什么译文没有写入文章？

系统会校验译文段落数。如果模型返回的译文段落数和原文段落数不同，系统会拒绝写入，避免中英文段落错位。可以重试翻译，或手动粘贴修订后的译文。

### 换电脑后为什么看不到原来的文章？

本地文章保存在当前浏览器的数据中，不会自动同步。可以在旧设备首页导出 JSON，再到新设备首页导入 JSON。

### 可以二次开发这个仓库吗？

本仓库是轻量运行版，不包含源码目录、依赖配置和开发脚本。二次开发请使用源码仓库：

[mikelian1/ppenglish](https://github.com/mikelian1/ppenglish)

## 安全提醒

不要把真实 DeepSeek API Key 写进：

- `README.md`
- `run.bat`
- `serve.py`
- 前端页面文件
- 截图
- 聊天记录
- Git 提交记录

轻量运行版推荐使用 Windows Credential Manager 或 `DEEPSEEK_API_KEY` 环境变量保存 API Key。

## 致谢

本项目最初受到以下项目启发，并在此基础上演化而来：

https://github.com/wushanglang/ppenglish

当前源码仓库围绕本地优先双语阅读、AI 整篇翻译、高亮、生词本和轻量运行流程做了较大幅度改造。源码和二次开发请见：

[mikelian1/ppenglish](https://github.com/mikelian1/ppenglish)
