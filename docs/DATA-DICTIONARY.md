# 字幕与切版定义

- 字幕 CSV 六列 `cue_id,track,format,in,out,text`。旧表头 `legacy_id,time_in,time_out` 对应 `cue_id,in,out`。UTF-8 可带 BOM。跨行引用从原件起始物理行定位。空串与 `-`、`N/A`、`NULL`、`未知` 都按缺字段处理。编号为字符串。同轨同号完整内容一致只采一条，冲突全组隔离。
- 源时钟固定为 30000/1001 帧每秒，目标为 24 帧每秒。`FRAME` 使用整数源帧。`DF` 用分号，非十整倍数分钟的首秒跳过标签 `;00`、`;01`，合法帧仍连续。`NDF` 用冒号并按名义 30 编号。`SRT`、`VTT` 代表以逗号或小数点分隔毫秒的时码列。墙钟以有理数换算源帧。
- 切版 `cut,start,end,target,kind` 用左闭右开源帧区间，类型为 `KEEP` 或 `REMOVE`。`KEEP` 必须给整数目标起帧，`REMOVE` 的 `target` 留空。源区间或目标区间重叠使整份切版失败。切版未覆盖区间是 `GAP`，即待证。
- 连续目标坐标为 `target + (源坐标 - start) × 1001/1250`。交付帧序号为落在区间内的整数网格点，因此两个端点都向上取整。显示出的目标重叠按轨道对交付整数帧做扫描线，重叠深度大于等于两条的每一帧只计一次。
- 源覆盖在同一轨内取并集，再对不同轨道累加。所有源帧量用十进制整数字符串或 `分子/分母`。原覆盖 = 已交付源覆盖 + 剪辑移除 + 待证。时码无效或身份矛盾无法估时，行数单计。证据 JSON 含原件、行证、散列、规则版本及归档 UTC。

## 实播回执核对（覆盖对账页下半部）

- 签发包 `packet_id,device_id,frame,cue_id,track,caption_text,caption_hash` 按目标帧逐帧签发；同一档号内帧号唯一。`caption_hash` 取字幕文本 SHA-256 前 12 位；给了 `caption_text` 时解析阶段先自校指纹，错配整单拒收。
- 设备回执 `receipt_id,device_id,frame,status,caption_hash,received_at,replay`。`status` 仅 `PLAYED`、`NOT_PLAYED`；`PLAYED` 必带指纹。`replay` 取 `1/true` 表示该帧为倒回重放。
- 帧级五状态：`PLAYED_OK` 播对（指纹一致）、`WRONG_CAPTION` 帧数播够但放错字幕（单列，不并入漏播）、`MISSED_CONFIRMED` 设备 `NOT_PLAYED` 确认没播、`PENDING_RECEIPT` 至今无任何回执（设备断线场景，不算漏播、不误报）、`REPLAY` 重放叠加标注（保留原状态，不抵销任何别处漏播）。
- 勾稽守恒：四状态帧数之和恒等于签发帧数；`REPLAY` 是帧上的标注位，不另占帧。漏播口径只含 `MISSED_CONFIRMED`。
- 回执以 `receipt_id` 幂等去重：相同 ID 的重试永不重复记账，采信数与去重数按次响应返回，存储内同号只留一条。晚到回执原地更新同一张核对单（档号不变，刷新 `updated_at`），`PENDING_RECEIPT` 随之转为实状态。
- 回执帧若不在签发包内，整批 422 拒收（`RECEIPT_UNKNOWN_FRAME`），不留半截账。核对单存于归档目录下 `playout/<run>.playbook.json`，与不可变签发证据分文件，可随回执演进。
