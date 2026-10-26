# 山东中职春考·单招学习软件

一个面向**山东省中职学生**的一站式备考学习软件：覆盖 **专升本 · 山东春考 · 单招 · 技能考试(含PLC) · 背单词 · 模拟卷 · 作文评分**，纯前端单页应用，可打包为 **Windows 桌面版(exe)** 与 **安卓手机版(APK)**。

## 功能一览

| 模块 | 说明 |
|---|---|
| 📚 专升本 | 词汇/语法/音标/阅读章节学习，自动记进度，章节评分 |
| 🏫 山东春考 | 中职春考语文·数学·英语真题章节练习，附解析与视频讲解 |
| 🎯 单招 | 山东单招语文·数学·英语真题，技能考试题库（含绘图/零件图/液压） |
| 🔧 技能·PLC | 单招技能考试理论题 + PLC 编程题，带图解与视频 |
| 📋 总结 | 春考/单招文言文、作文写法、阅读题型、英语题型、数学公式题型方法论 |
| 📄 模拟卷 | 按春考/单招真实试卷排版自动组卷（语文·数学·英语），一题一答 |
| 📖 背单词 | 中职 2600 词 / 高考 3500 词（词频标记：高频/中频/低频），每日打卡、生词本、错词复习、今日默写、报词听写（念汉字本子上写，间隔可调） |
| ✍️ 作文评分 | 拍照/粘贴作文，本地智能评分（语文 45 分制、英语 10 分制，按山东春考口径），支持联网 AI 深度点评 |

**通用能力**：错题本（自动收录错题与生词）、通关难度可调（题量 20/40 等）、检查更新（GitHub Release + 镜像源）、进度本地保存、数据兜底（题库文件缺失不白屏）。

## 技术栈

- **前端**：原生 HTML/CSS/JavaScript 单页应用（无框架、无构建依赖，`App/index.html` 直接浏览器打开即可运行）
- **桌面版**：Python 3 + [pywebview](https://pywebview.flowrl.com/)（`launcher.py` 为入口），PyInstaller 打包为单文件 exe
- **安卓版**：Capacitor（`study-app-apk` 工程）打包 WebView APK
- **更新分发**：GitHub Releases + `update.json`（主源 raw + ghfast.top / gh-proxy.com 镜像，实时回源无缓存延迟）

## 目录结构

```
App/
  index.html       主界面与全部交互逻辑（含手机端适配 CSS）
  data.js          词汇库与基础题库（APP_DATA）
  chunkao_data.js  山东春考真题题库（CK_DATA）
  danzhao_data.js  山东单招真题 + 技能/PLC 题库（DZ_DATA / JN_DATA）
  guide.js         使用引导文案
  zz2600_data.js   中职 2600 词（词频标注，ZZ2600_WORDS）
launcher.py        Windows 桌面版入口（pywebview 壳）
```

## 构建

**桌面版 exe**（需 Python 3 + PyInstaller + pywebview）：

```bat
pyinstaller --onefile --noconsole --name "专升本章节学习" --add-data "App;App" launcher.py
```

**安卓 APK**：将 `App/` 作为 Capacitor Web 资源（`www/`），`npx cap sync android` 后 `gradlew assembleDebug` 即可。

> 提示：桌面版内置 OCR 与本地评分依赖 `rapidocr_onnxruntime` / `onnxruntime` / Windows 原生 OCR（winrt），打包时请一并打入对应依赖。

## 数据来源声明

- **真题**：收录自山东省春季高考、高职单招公开考试真题及历年权威模拟卷（公开发布的考试原题）。
- **词汇表**：词表依据《高考英语词汇3500词（词频标记版）》整理，词频（高频/中频/低频）按原表映射；中职 2600 词对照中职英语课标核心词整理。
- **未附答案的题目**均如实标注，不编造答案。
- 本软件为学习辅助工具，**作文 AI 评分仅供参考，不替代老师**。

## 许可证

[MIT](./LICENSE) © 2026 llluuu995

## 免责声明

本软件仅供个人学习交流使用。题库数据来源于公开考试资料，版权归原作者/出题机构所有，若有侵权请联系删除。
