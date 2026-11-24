# 深度登记 字幕交付校对册

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 字幕文件采信 | 核对逐行隔离与重复字幕 | `/sheet/source` `/api/check/source` | `app/modules/source/service.py` | `tests/test_source.py` |
| M2 帧率与丢帧约束 | 复查非法标签与精确换算 | `/sheet/clock` `/api/check/clock` | `app/modules/clock/timecode.py` | `tests/test_clock.py` |
| M3 切版段映射 | 按切版重建目标帧 | `/` `/api/check/edits` | `app/modules/edits/contract.py` `app/modules/edits/mapping.py` | `tests/test_edits.py` |
| M4 字幕冲突定位 | 定位同轨重叠帧与原行组 | `/sheet/overlaps` `/api/check/overlaps` | `app/modules/overlaps/service.py` | `tests/test_overlaps.py` |
| M5 时长与丢段对账 | 查看并集覆盖守恒 | `/sheet/balance` `/api/check/balance` | `app/modules/balance/service.py` | `tests/test_balance.py` |
| M6 批次留档复跑 | 保存原件并逐值复算 | `/sheet/runs` `POST /api/runs` | `app/modules/runs/files.py` `app/modules/runs/service.py` | `tests/test_runs.py` |
| M7 交付证据签发 | 下载经散列核验的交付证据 | `/sheet/delivery` `/api/delivery/<key>/export` | `app/modules/delivery/checks.py` | `tests/test_delivery.py` |
| M8 实播回执核对 | 按签发包逐帧勾对实播回执 | `/sheet/balance` `/api/playout/<key>` | `app/modules/playout/ledger.py` `app/modules/playout/service.py` | `tests/test_playout.py` `tests/test_playout_api.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-02 | 脏字幕首列 BOM | 首列无效 | 去首 BOM | `app/modules/source/reader.py` | `tests/test_source.py::test_bom_and_alias` |
| TRAP-04 | 脏字幕重复表头 | 当成字幕计算 | 单列分段 | `app/modules/source/reader.py` | `tests/test_source.py::test_repeated_header` |
| TRAP-05 | C112 多余列 | 文本错位 | 保留整行隔离 | `app/modules/source/reader.py` | `tests/test_source.py::test_width_and_missing` |
| TRAP-07 | C110 时码 N/A | 当成零帧 | 隔离必填空值 | `app/modules/source/service.py` | `tests/test_source.py::test_width_and_missing` |
| TRAP-09 | 9007199254740993 | 浏览器数值吞位 | 字符串保形 | `app/modules/source/service.py` | `tests/test_source.py::test_string_identity` |
| TRAP-10 | C104 使用分数帧率 | 假设 30 或先舍入 | 保留端点有理数至最后 | `app/modules/clock/timecode.py` | `tests/test_clock.py::test_exact_rate` |
| TRAP-14 | C111 内容相撞 | 后稿静默覆盖 | 同号矛盾整组隔离 | `app/modules/source/service.py` | `tests/test_source.py::test_conflicting_revision` |
| TRAP-17 | `legacy_id` 旧表头 | 硬读当前字段失败 | 按列别名迁移 | `app/modules/source/service.py` | `tests/test_source.py::test_bom_and_alias` |
| TRAP-23 | C115 与 C116 首尾相接 | 共同边界算重叠 | 半开区间扫线 | `app/modules/overlaps/sweep.py` | `tests/test_overlaps.py::test_touch_is_not_overlap` |
| TRAP-26 | 设备断线未收回执 | 直接判漏播误报 | 单列为 `PENDING_RECEIPT`，漏播只认 `NOT_PLAYED` | `app/modules/playout/ledger.py` | `tests/test_playout.py::test_pending_receipt_not_false_missed` |
| TRAP-27 | 倒回重放补帧 | 抵销别处漏播 | 重放只加标注位，原状态与漏播账不动 | `app/modules/playout/ledger.py` | `tests/test_playout.py::test_replay_never_offsets_missed_elsewhere` |
| TRAP-28 | 播够帧数但字幕放错 | 计入播对或漏播 | 指纹不符单列 `WRONG_CAPTION` | `app/modules/playout/ledger.py` | `tests/test_playout.py::test_wrong_caption_listed_separately` |
| TRAP-29 | 同一回执网络重试 | 重复记账 | 按 `receipt_id` 幂等去重，晚到回执更新原核对单 | `app/modules/playout/service.py` | `tests/test_playout.py::test_duplicate_receipt_id_counted_once` |

## 守恒与范围

脏样例 1140 源帧 = 740 交付 + 200 移除 + 200 待证。65 个重叠目标帧独立记录，5 条隔离记录无法量化。原件为带格式列的供应商抽取 CSV，DF 参数固定为 29.97，目标固定 24 fps。

实播核对单（样例 24 个签发帧）守恒：`PLAYED_OK + WRONG_CAPTION + MISSED_CONFIRMED + PENDING_RECEIPT = 24`，`REPLAY` 为叠加标注不占帧。首批回执下 6 帧回执未到、3 帧确认没播、1 帧放错字幕、2 帧重放；并入晚到回执后未到清零、核对单档号不变，确认没播仍为 3 帧。
