---
name: ltx-video-colab
description: Generate videos with sound, and voice or sound clips (TTS), using LTX-2.5 on the user's own Google Colab GPU, driven from this computer through google-colab-cli. Use when the user asks to 生成影片／延伸影片／把分鏡做成影片／用一張圖做成影片／用角色設定表固定角色／配音／旁白／音效, or wants clips made from text, a start image, first/last frames, or a character reference sheet. Colab only (needs Google AI Pro; the user's computer needs no GPU).
---

# LTX-2.5 影片與配音（Colab GPU）

用 Lightricks 的 LTX-2.5（開放權重，影像和聲音一起生成），在使用者自己的 Colab GPU 上跑。
你負責理解需求、寫提示詞、組工作清單、檢查成果；生成在 Colab 上的 ComfyUI 裡跑。

| type／mode | 做什麼 |
|---|---|
| `video` + `text` | 純文字生影片（有聲音） |
| `video` + `image` | 一張起始圖往下演 |
| `video` + `frames` | 指定首格、尾格，或兩者都給 |
| `video` + `extend` | 接著前一段往下演，自動接回原片 |
| `video` + `ref` | 依角色設定表（Ingredients IC-LoRA）生成，每一格都參考設定表；可再加一張起始圖 |
| `tts` | 只要聲音：說話、旁白、音效、環境音 |

**做不到的**（要用的話請使用者另找工具）：生圖／改圖、訓練自己的角色或畫風 LoRA、參考聲音的音色（固定某個人的聲音）。

---

## 0. 第一次使用：先說清楚，再安裝

如果 `python scripts/ltxrun.py check` 找不到 colab 或還沒登入，先停下來，用使用者的語言說明這幾件事，等對方說「好」才開始：

1. **會做什麼**：在使用者的 Google 帳號開一台 Colab GPU，裝 ComfyUI＋LTX-2.5，生成完把檔案下載回這台電腦，然後關掉 GPU。
2. **要什麼訂閱**：至少 Google AI Pro（附 Colab 運算單元）。
3. **花多少點**：L4 約每小時 1.5 點，G4 約 11 點。AI Pro 每月固定有 200 點（效能等級同 Colab Pro，Colab Pro 本身是 100 點；以使用者帳號的 `ltxrun.py check` 實際餘額為準）。每次開機在 Colab 上下載約 40 GB 模型。L4 實測：480P、5～7 秒一段約 75～110 秒；開機加下載約 5～9 分鐘；一批 5 段左右約 0.3～0.5 點。720P／1080P、G4 和 `frames` 模式還沒實測，第一次用先試一段。
4. **會從哪裡抓什麼**：GitHub 的 ComfyUI 和 Lightricks 官方的 ComfyUI-LTXVideo 節點組（都固定版本）；Hugging Face 的 Lightricks/LTX-2.5（固定版本）。用到 `ref` 模式時，另外抓 Lightricks/LTX-2.5-22b-IC-LoRA-Ingredients（1.2 GB，固定版本並核對 SHA256；這也是受限模型，要另外在它的頁面同意條款）。全部下載到 Colab 上，不佔這台電腦的空間。
5. **何時要登入**：只有第一次。給使用者一個 Google 網址，他登入、按允許、把授權碼貼回來。token 存在 `~/.config/colab-cli/token.json`，只有使用者自己讀得到。
6. **授權**：LTX-2 Community License，年營收低於 1,000 萬美元的個人或公司可以免費商用；細節以 Lightricks 的 LICENSE 為準。

同意後問一個選擇（沒回答就用預設，記住答案）：
- **要用更快的 G4 嗎？**（預設 L4。L4 影片預設 480P，G4 預設 720P）

安裝照 repo 的 `INSTALL_FOR_AGENTS.md`。登入：
```
python scripts/colab_login.py url
python scripts/colab_login.py code <授權碼>
python scripts/ltxrun.py check
```

---

## 1. 每次生成的流程

1. **問清楚要什麼**：幾段影片、每段幾秒、直式或橫式、有沒有起始圖或首尾格、台詞、要不要另外的配音或音效。
2. **準備輸入檔**：放進工作資料夾，例如 `ltxjob/inputs/`。**所有檔案都要在 manifest 所在的資料夾裡面**，不能用絕對路徑或 `..`，否則程式會拒絕開機。
3. **寫提示詞**：照 `references/prompt-guide.md`。
4. **寫 `manifest.json`**：格式見 `references/manifest.md`。影片和配音可以放在同一批，一次開機做完。
5. **確認規格**：兩段以上的影片，一定要先跟使用者確認解析度、比例、秒數。`ltxrun.py` 沒有 `--confirmed` 不會開機，會先印出摘要給你轉給使用者。
6. **送出**：
   ```
   python scripts/ltxrun.py run ltxjob/manifest.json --gpu L4
   ```
   成品在 `ltxjob/out/`：影片 `<id>.mp4`，配音 `<id>.wav`。
7. **檢查成果**：影片至少抽幾格看＋聽聲音；配音整段聽過。有問題只重做那一段（改 prompt 或 seed）。
8. **回報，問要不要保留 GPU**：做完 GPU 先留 15 分鐘。一定要問：
   「要繼續生成或修改嗎？要的話 GPU 先留著（L4 一小時約 1.5 點）；不用的話我現在關掉。」
   - 繼續 → 下一批加 `--session <名字>`
   - 多留 → `python scripts/ltxrun.py keep --session <名字> --minutes 60`（最多 240）
   - 關掉 → `python scripts/ltxrun.py stop --session <名字>`
   - 沒回答：本機計時器 15 分鐘後自動關機，對話結束了也會關。

中途失敗或被中斷的批次一律馬上關機。`python scripts/ltxrun.py sessions` 列出開著的 GPU。

---

## 2. 你要替使用者決定的

### 影片模式
| 情況 | 用 |
|---|---|
| 有現成畫面（角色照、場景圖、分鏡圖）要動起來 | `image` |
| 動作必須落在某個姿勢、換場要精準銜接 | `frames` |
| 空景、氣氛、快速試想法 | `text` |
| 「接著往下演」「再長一點」 | `extend` |
| 角色要長時間維持同一張臉（長台詞、大特寫） | `ref`（設定表＋起始圖） |

### 角色一致性
LTX-2.5 只認得畫面，不會「看著照片畫臉」。只用文字描述的角色，每段都會是不同的人，年輕角色還常被畫老。

1. **有臉的鏡頭一律給起始圖**（`image`）：把角色設定表的正面像去背，合成到場景裡當第一格，臉佔畫面高度至少 1/4。這是預設做法，快、畫質好、動作照提示詞走。
2. **臉要在整段裡都不走樣**時，改用 `ref`：設定表在每一格都當參考，再加同一張起始圖。實測（L4、10 秒、含轉頭）：臉比純起始圖更穩、更接近設定表；但動作和光線變化會變少，生成時間約 4.5 倍，輸出固定 960×544、不經過放大。
3. 只給設定表、不給起始圖的 `ref`：場景會照提示詞生成，但臉只是「像」，構圖也比較難控制。

設定表要乾淨：一個角色、純色背景、沒有文字或標註線（臉部特寫｜正面｜側面並排最好）。標註文字和線條會被當成畫面的一部分。

### 什麼時候用 `tts`
- 影片本身就會有聲音和對白；**只有需要獨立的聲音檔時**才用 `tts`：旁白、廣播劇、音效、要另外剪進去的台詞。
- 每段 `tts` 的聲音是重新生成的，同一個角色在不同段落的聲音不保證一樣。

### 解析度與長度
- 影片：`480P`／`720P`／`1080P`；比例 `16:9` 或 `9:16`。
- 一段 2–20 秒（影片和配音都是）。更長就切段，影片可以用 `extend` 接。
- 試拍 480P、5 秒；定稿 720P。

---

## 3. 失敗時

先看 `references/troubleshooting.md`。最常見：
- 沒登入或 token 過期 → 重跑 `colab_login.py url`。
- 分配不到 GPU → 等一下或換 L4；不要改 A100。
- 某段失敗 → 讀 `out/results.json` 的 error，只重送那一段。
- 中途斷線 → 先 `ltxrun.py sessions`，有殘留就 `stop`。
