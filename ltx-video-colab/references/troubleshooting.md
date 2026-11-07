# 排錯

先跑 `python scripts/ltxrun.py check`，看三件事：colab 指令在不在、有沒有登入、剩幾點。

## 一定要記得的：沒關的 GPU 會一直扣點
- `ltxrun.py run` 順利做完時，GPU 先留 15 分鐘（`--idle-minutes`）等下一批，由本機的獨立計時器到時自動 `stop`；失敗或中斷的批次馬上 `stop`。計時器的紀錄在 `~/.config/ltxskill/keep/<session>.log`。
- 本機程式被強制中斷、電腦睡著、網路斷掉時，**遠端那台不會自己停**。回來第一件事：
  ```
  python scripts/ltxrun.py sessions
  python scripts/ltxrun.py stop --all
  ```
- 對話結束前，確認 `sessions` 是空的。

## 安裝與登入
| 症狀 | 原因與處理 |
|---|---|
| `No module named 'termios'`（Windows） | colab-cli 的互動終端只支援 Linux／macOS。安裝腳本會打補丁；手動處理：重跑 `install/install.ps1` |
| `WebSocketConnectionClosedException: socket is already closed`（Windows） | colab-cli 0.7.5 的問題。安裝腳本固定裝 **0.7.4** |
| `colab` 指令跑起來先去檢查更新、卡住 | `~/.config/colab-cli/settings.json` 寫 `{"enable_update_check": false}`（安裝腳本會寫） |
| 登入後 `redirect_uri_mismatch` | 一定要用 `colab_login.py`（它用 colab-cli 自己的 client 與 redirect），不要自己拼網址 |
| `invalid_grant` | 授權碼只能用一次、幾分鐘內有效：重跑 `colab_login.py url` |
| 換帳號 | 刪掉 `~/.config/colab-cli/token.json` 再登入 |
| 不用的時候想收回權限 | 到 Google 帳戶的「第三方應用程式和服務」移除 colab-cli，要用時重新登入 |

## 開機
| 症狀 | 處理 |
|---|---|
| `manifest 有問題，沒有開機` | 照訊息修 manifest。最常見：檔案路徑在 manifest 資料夾外面、`seconds` 超出 2–20、`tts` 放了檔案 |
| 點數夠卻分配不到 GPU | 尖峰時段常見。等幾分鐘再試，或改 L4／G4。**不要改 A100**（貴很多） |
| GPU 名字打錯 | colab-cli 會默默開成 A100。`ltxrun.py` 只接受 L4、G4、A100、H100 |
| `GPU capability ... cannot run the int8 LTX-2.5 weights` | 拿到 T4（太舊），換 L4 以上 |
| `ComfyUI is at ..., expected ...` 或 `ComfyUI-LTXVideo is at ...` | VM 上的程式不是固定的版本：`stop` 這台，重開一台 |
| `沒有登入`／`401` | token 過期或被撤銷：重跑登入 |

## 生成
| 症狀 | 處理 |
|---|---|
| 一段失敗，其他成功 | 看 `out/results.json` 那一段的 `error`；只重送那一段（可加 `--session` 沿用還開著的機器） |
| L4 上 `out of memory` | 先降到 480P、縮短秒數；還是不行就改 G4 |
| 畫面上出現字 | 提示詞加 `no text, no subtitles` |
| 動作很少、像照片在晃 | 提示詞把動作照時間順序寫清楚，加上攝影機運動 |
| 起始圖的人一動就變形 | 動作改小、秒數縮短，或改用 `frames` 給尾格 |
| 台詞被吃掉或講太快 | 台詞太長：縮短台詞或加長秒數（中文約每秒 4 個字） |
| 延伸的那段接起來會跳 | 提示詞的人物、光線、聲音描述跟上一段對齊 |
| `遠端回報了不合規的檔名，不下載` | VM 回報的檔名不是 `<id>.mp4`／`<id>.wav`。這不該發生：`stop` 這台，重開再跑；一再出現就不要再用這台機器 |
| `that job has not produced a file` | `@id` 指向的 job 排在後面或失敗了 |
| 進度一直停在 `models` | 第一次要下載約 40 GB；超過 15 分鐘看 Hugging Face 狀態 |
| `models` 失敗，錯誤是 `401 … gated repo` | LTX-2.5 是受限模型：請使用者在 https://huggingface.co/Lightricks/LTX-2.5 同意條款、建立 Read 權杖，並在自己的終端機設定環境變數 `HF_TOKEN`（Windows：`setx HF_TOKEN "<權杖>"` 後開新終端機）。不要請使用者把權杖貼到對話裡 |

## 想看遠端的完整紀錄
```
colab exec -s <session> -f <一個只有 print(open('/content/ltxjob/remote_job.log').read()[-5000:]) 的檔案>
```
ComfyUI 的紀錄在 `/content/comfyui.log`。

## 檔案回傳
- 用 `colab download` 一個一個抓。只會抓 `<id>.mp4`／`<id>.wav`，其他檔名一律拒絕。
- **不要**把影片轉成文字印在 log 裡傳回來，會慢幾十分鐘而且一直扣點。

## 參考過的前人經驗
- dseditor/h3-colab-skill（MIT）：這個 fork 的原版。開關機、計時器、點數保護都沿用它的設計。
- bockybocky/colab-gpu-runner（MIT）：Windows 上固定 0.7.4＋補丁、短 exec 比長 exec 穩、結束一定檢查殘留 runtime、不要用 log 傳檔。
- Google 的 google-colab-cli（Apache-2.0）：登入流程（client、scope、redirect）照它的 `auth.py`。
