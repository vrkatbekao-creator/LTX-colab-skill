# manifest.json

放在工作資料夾裡；`image`／`first`／`last`／`extend` 的路徑都**相對於 manifest 所在的資料夾**，而且必須在這個資料夾裡面（不能用絕對路徑、`..` 或指到外面的捷徑，否則不會開機）。
成品下載到同一個資料夾的 `out/`：影片 `<id>.mp4`，配音 `<id>.wav`，總結在 `out/results.json`。

```json
{
  "gpu": "L4",
  "stop_on_error": false,
  "jobs": [
    {"id": "shot01", "type": "video", "mode": "image", "image": "inputs/lin_library.png",
     "prompt": "Use the provided start image as the first frame. ...",
     "seconds": 6, "aspect": "9:16", "resolution": "720P"},

    {"id": "shot01b", "type": "video", "extend": "shot01",
     "prompt": "She closes the book and stands up ...", "seconds": 5},

    {"id": "shot02", "type": "video", "mode": "frames",
     "first": "inputs/door_closed.png", "last": "inputs/door_open.png",
     "prompt": "...", "seconds": 4, "aspect": "16:9"},

    {"id": "establish", "type": "video", "mode": "text",
     "prompt": "Wide shot of a quiet library at dusk ...", "seconds": 5},

    {"id": "narration01", "type": "tts", "seconds": 8,
     "prompt": "A calm middle-aged man speaking in Mandarin, saying: \"那天晚上，圖書館比平常安靜。\""}
  ]
}
```

## 欄位

| 欄位 | 用在 | 說明 |
|---|---|---|
| `id` | 全部 | 英數、`-`、`_`（1–60 字）；也是輸出檔名 |
| `type` | 全部 | `video`（預設）或 `tts` |
| `prompt` | 全部 | 見 prompt-guide.md |
| `mode` | video | `text`（預設）、`image`、`frames` |
| `image` | video(image) | 起始圖 |
| `first`／`last` | video(frames) | 首格／尾格，至少一張 |
| `extend` | video | 前面某個影片 job 的 `id`（同一批），或一支影片檔路徑；會拿它的最後一格當起始圖，成品自動接在原片後面。不能和 `image`／`first`／`last` 一起用 |
| `seconds` | 全部 | 2–20（預設 5） |
| `aspect` | video | `16:9`（預設）、`9:16` |
| `resolution` | video | `480P`、`720P`、`1080P`；不給就看 GPU（L4 480P，G4 720P） |
| `negative` | 全部 | 不想要的東西；不給就用官方範本的預設 |
| `seed` | 全部 | 不給就隨機；要重現就固定 |
| `timeout` | 全部 | 單段最多等幾秒（影片預設 2400，配音 900） |

`tts` 只吃文字：放了 `image`、`voices` 之類的檔案欄位會被拒絕（不支援參考聲音）。

## 一批的順序與 `@id`
同一批依序執行。`image`、`first`、`last`、`extend` 可以寫 `@<id>`，意思是「**用這一批裡前面那個影片 job 的成品**」（取它的最後一格）。`extend` 寫裸的 `id` 也可以，會自動當成 `@id`。
被引用的 job 一定要排在前面、而且是影片；引用配音（`tts`）會被拒絕。被引用的 job 失敗時，這一段也會失敗（其他段照跑）。

## 續跑
`out/` 裡已經有 `<id>.mp4`／`<id>.wav` 的 job 會跳過；後面用 `@id` 指向它的，會改用本機那個檔案。要重做加 `--force`。
