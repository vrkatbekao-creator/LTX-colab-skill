# LTX-2.5 影片與配音 Skill（Colab GPU）

讓 Claude、Codex、Antigravity 這類 AI，**在你自己的 Google Colab GPU 上**用 Lightricks 的 LTX-2.5 生成：

- 🎬 **影片（有聲音）**：純文字、一張起始圖、首尾格
- 🧵 **延伸**：接著上一段往下演，自動接回原片
- 🎙 **配音／音效（TTS）**：旁白、台詞、音效、環境音

AI 負責理解需求、寫提示詞、整理工作清單、檢查成果；生成全部在 Colab 上跑。**你的電腦不需要顯示卡。**

> 這是 [dseditor/h3-colab-skill](https://github.com/dseditor/h3-colab-skill) 的 fork。
> 原版用 MiniMax H3；這個版本換成 LTX-2.5，並做了一輪安全修正。差異見下方〈這個 fork 改了什麼〉。

**做不到的**：生圖／改圖、多張參考圖鎖角色、參考聲音的音色。需要這些請另找工具。

---

## 一行安裝（貼給你的 AI）

```text
請照 https://github.com/vrkatbekao-creator/h3-colab-skill/blob/main/INSTALL_FOR_AGENTS.md 幫我安裝 ltx-video-colab 這個 skill：開始之前先跟我說明它會做什麼、要什麼訂閱、何時要登入，我同意後再安裝。
```

安裝完只需要**登入一次**：AI 給你一個 Google 網址，用有 AI Pro 的帳號登入、按允許，把畫面上的授權碼貼回對話。

## 需要什麼

| | |
|---|---|
| 訂閱 | **Google AI Pro**（附 Colab 運算單元，每月固定 200 點，等同兩份 Colab Pro） |
| 這台電腦 | Windows／macOS／Linux 都可以；會裝 `uv`（固定 0.13.7）、Python 3.12 與 Google 的 `google-colab-cli` 0.7.4（獨立環境） |
| AI | 能在你電腦上執行指令的 AI：Claude Code／Claude 桌面版、Codex、Antigravity… |

| GPU | 每小時 | 每月 200 點約可用 |
|---|---|---|
| **L4** | 約 1.5 點 | 約 133 小時 |
| **G4** | 約 11 點 | 約 18 小時 |

每次開機要在 Colab 上裝環境＋下載約 40 GB 模型。**LTX-2.5 在 L4 上的速度和記憶體還沒實測**：第一次請先跑一段 480P、5 秒。

## 它怎麼保護你的點數

- 開機前先查剩餘運算單元，不到 5 點不開。
- GPU 只接受 L4／G4／A100／H100（Colab CLI 打錯字會默默開成 A100）。
- 每批有時間上限（預設 120 分鐘）。
- 做完先把 GPU **留 15 分鐘**等你決定；沒有回答的話，電腦上的獨立計時器 15 分鐘後自動關機。
- 中途失敗或被中斷的批次**馬上關機**；最後再檢查帳號上有沒有殘留的機器。

## 這個 fork 改了什麼

**換模型**
- MiniMax H3 → **LTX-2.5**。H3 的授權排除歐盟、英國、韓國、美國；LTX-2.5 的授權是全球授權，只排除受全面制裁的國家或地區。
- 影片工作流照 ComfyUI 官方的 LTX-2.5 範本重建，只用 ComfyUI 內建節點。
- 配音用 Lightricks 官方節點組的純音訊模式。
- 拿掉 H3 Toybox 和三個個人維護的節點組；拿掉生圖（LTX-2.5 不能生圖）。

**安全修正**
- **固定版本**：ComfyUI、Lightricks 節點組、LTX-2.5 模型都固定在特定 commit／revision，開機時檢查，不對就停。原版每次抓最新版。
- **路徑穿越**：VM 回報的檔名只接受 `<id>.mp4`／`<id>.wav`；原版會照 VM 給的路徑寫進你的電腦。
- **輸入檔範圍**：manifest 裡的檔案必須在工作資料夾裡面（擋 `..`、絕對路徑、捷徑）。原版可以上傳電腦上任何檔案。
- **登入 token**：存檔時設成只有你自己讀得到。
- **安裝位置**：只裝進已經存在的 Claude Code、Codex、Antigravity、`~/.agents` 資料夾；uv 安裝腳本固定版本。
- **拿掉本地模式**：原版的本地模式會在你電腦上跑第三方節點組，並開一個沒有驗證的本機 API。

**還沒做到的**
- 沒有在真的 GPU 上跑過。工作流有對照 ComfyUI 原始碼做靜態檢查，安全相關的邏輯有單元測試，但第一次請當作試跑。
- 配音的設定是從官方 LTX-2.3 範本類推的。
- VM 上 `pip install` 的套件版本沒有全部鎖死（ComfyUI 和節點組的 requirements 用的是 `>=`）。這部分只影響 Colab VM。

## 檔案

```
ltx-video-colab/              ← 裝進 AI 的 skill
  SKILL.md                    流程與判準
  scripts/ltxrun.py           本機：檢查、開機、上傳、監看、下載、關機
  scripts/colab_login.py      兩段式登入（AI 給網址 → 你貼授權碼）
  remote/remote_job.py        在 Colab 上跑：裝環境、下載模型、逐一生成
  remote/ltx_graph.py         LTX-2.5 的 ComfyUI 工作流（影片三種模式＋配音）
  references/                 manifest 格式、提示詞寫法、排錯
install/                      install.ps1（Windows）、install.sh（macOS／Linux）
INSTALL_FOR_AGENTS.md         給 AI 看的安裝步驟
```

## 授權與來源

- 本 repo：MIT（沿用原版，見 LICENSE）。
- 原版：[dseditor/h3-colab-skill](https://github.com/dseditor/h3-colab-skill)（DSLab 夢想空間實驗室 · 松音）。
- 模型：[Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5)，LTX-2 Community License Agreement（年營收 1,000 萬美元以上需要另外的商業授權；請先讀 LICENSE）。
- 節點組：[Lightricks/ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo)（LTX-2 Community License）。
- 工作流依據：[Comfy-Org/workflow_templates](https://github.com/Comfy-Org/workflow_templates) 的 LTX-2.5 範本。
- [google-colab-cli](https://pypi.org/project/google-colab-cli/)（Google，Apache-2.0）；登入流程照它的 `auth.py`。
- 前人經驗：[bockybocky/colab-gpu-runner](https://github.com/bockybocky/colab-gpu-runner)（MIT）的 Windows 補丁與排錯原則。
