# 提示詞寫法（LTX-2.5）

依據 Lightricks 官方的提示詞指南：
- https://docs.ltx.io/open-source-model/usage-guides/prompting-guide
- https://ltx.io/blog/ltx-2-5-prompt-guide
- 純音訊：https://docs.ltx.io/open-source-model/feature-guides/audio/text-to-audio

讀得到的話先讀官方版本；下面是最低限度的規則。

## 影片

- **英文、現在式、一段連貫的散文**，不要寫成關鍵字清單。
- 涵蓋六件事（官方指南的六個元素）：**鏡頭**（景別）、**場景與光線**、**動作**、**人物**（外觀、服裝、表情）、**攝影機運動**、**聲音**。
- 照時間順序寫：先發生什麼、再發生什麼、最後畫面停在哪裡。秒數越長，要寫的事件越多。
- **攝影機用官方詞彙**：`pushes in`、`pulls back`、`pans across`、`circles around`、`tracks`、`static frame`。寫出移動結束時畫面裡有什麼，比只寫方向好。
- 一段只用一種景別；要換鏡頭就分段，或在同一段裡明確寫「cut to」。
- **對白**：說話的人＋語言＋引號，例如
  `A young woman speaking in Mandarin, saying: "有人在那裡嗎？"`
  台詞長度要跟秒數相符；太長會吃字，太短會停頓。
- 聲音另外寫一句：環境音、動作聲、有沒有音樂（不要音樂就寫 `no music`）。
- 不想要畫面上出現字：寫 `no text, no subtitles`。

### `image` 模式
- 開頭寫 `Use the provided start image as the first frame.`
- 接著只寫**接下來發生什麼**；畫面裡已經有的東西不用重新描述，但人物外觀不要寫得跟圖片矛盾。
- 動作從小開始：一張靜止的圖要一下子大動作，容易變形。

### `frames` 模式
- 首尾格用同樣的比例、相似的光線；描述的是**兩格之間的動作**。

### `extend`
- 程式會拿上一段的最後一格當起始圖，所以照 `image` 模式寫，只寫接下來發生什麼。
- 人物外觀、光線、聲音的描述要跟上一段一致，接起來才不會跳。

## 配音（`tts`）

- 描述聲音本身：**誰在說（性別、年紀、嗓音特質）＋語言＋引號裡的台詞**，例如
  `An old man says in a raspy, deep voice, in Mandarin: "今天天氣真好，我們出去走走吧。"`
- 音效或環境音也可以：`Heavy rain on a tin roof, distant thunder, no music.`
- 秒數抓台詞長度：中文大約每秒 4 個字。
- 每一段都是重新生成的聲音，同一個角色跨段落的音色不保證一致；需要固定某人的聲音，請使用者用別的工具。
