# 字幕交付校对册

字幕编辑核对公映版切段、供应商字幕与 24 fps 目标。网格按原行、入出帧与原因定位交付风险。

## 启动与演示

`docker compose up --build` 后打开 `http://localhost:18465`。本机安装 `requirements.txt` 后可运行 `flask --app app.main run -p 18465`。用 `pytest -q` 执行测试。归档目录默认 `var/cuts`，由 `CAPTION_ARCHIVE` 配置。

- 首页检查 C101 跨三段，C103 在 B-01 与 B-02 间留下 200 源帧缺证。网格支持方向键和鼠标选格。
- 帧率校核查 C105 的非法丢帧号。冲突定位查三条字幕同占 28 个目标帧，覆盖账中重叠另外记录。
- 文件采信可提交自有 CSV。归档校对后，在版本归档复算，在交付签发下载一份 JSON 证据包。
- 覆盖对账页下半部按签发包逐帧勾对实播回执：设备确认没播（`MISSED_CONFIRMED`）与未收到回执（`PENDING_RECEIPT`，不误报漏播）分列；播够帧数但放错字幕单列 `WRONG_CAPTION`；倒回重放只标注、不抵销别处漏播。同号回执重试幂等去重，晚到回执原地更新同一张核对单。样例可用「并入晚到回执」链接对照首批/补齐两版。

## API

`POST /api/runs` 接受 `{"sample":"dirty"}`、`{"sample":"clean"}` 或含 `cues` 与 `cuts` CSV 文本的 JSON。`GET /api/check/<sheet>` 查 `source`、`clock`、`edits`、`overlaps`、`balance`，用 `run` 查询归档或用 `sample` 预览。归档详情 `GET /api/runs/<id>`，复算 `POST /api/runs/<id>/repeat`，下载 `GET /api/delivery/<id>/export`。

实播回执对账挂在归档档号下：`POST /api/playout/<id>/packets` 用签发包 CSV 建立核对单（重复建档 409），`POST /api/playout/<id>/receipts` 接回执 CSV 或单条回执 JSON，返回本次采信数与去重数并更新原单；`GET /api/playout/<id>` 查当前核对单；`POST /api/playout/preview` 不落档试算。

[数据定义](docs/DATA-DICTIONARY.md) · [深度登记](docs/DEPTH.md) · [复算例](docs/FRAME-EXAMPLE.md)

前五张业务页也可用 `POST /api/check/<sheet>` 直接提交样例或原件，只试跑到选中的校对阶段。
