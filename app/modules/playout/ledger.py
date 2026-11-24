"""签发包与实播回执的帧级对账引擎。

状态约定（设备确认没播与未收到回执严格分开）：
- PLAYED_OK          设备回执 PLAYED 且字幕指纹与签发包一致
- WRONG_CAPTION      设备回执 PLAYED（帧数播够）但字幕指纹不符，单列
- MISSED_CONFIRMED   设备回执 NOT_PLAYED，设备确认该帧没播
- PENDING_RECEIPT    签发包有帧但至今没有任何回执，不算漏播
- REPLAY             倒回重放帧，只标注，不抵掉任何别处的漏播
"""

from collections import OrderedDict, defaultdict

# 帧级核对状态
PLAYED_OK = 'PLAYED_OK'
WRONG_CAPTION = 'WRONG_CAPTION'
MISSED_CONFIRMED = 'MISSED_CONFIRMED'
PENDING_RECEIPT = 'PENDING_RECEIPT'
REPLAY = 'REPLAY'

STATUSES = (PLAYED_OK, WRONG_CAPTION, MISSED_CONFIRMED, PENDING_RECEIPT, REPLAY)
# 倒回重放不计入任一播对账口径，漏播只认设备确认
FRAME_STATES = (PLAYED_OK, WRONG_CAPTION, MISSED_CONFIRMED, PENDING_RECEIPT)

STATUS_LABELS = {
    PLAYED_OK: '播对',
    WRONG_CAPTION: '放错字幕',
    MISSED_CONFIRMED: '确认没播',
    PENDING_RECEIPT: '回执未到',
    REPLAY: '倒回重放',
}


def _blank_frame(row):
    return dict(frame=int(row['frame']), packet_id=row['packet_id'], cue_id=row['cue_id'],
                track=row['track'], expected_hash=row['caption_hash'], device=None,
                state=PENDING_RECEIPT, actual_hash=None, replayed=0, receipt_ids=[])


def build_ledger(packets, receipts):
    """根据签发包行与已去重的回执行重建帧核对单。

    纯函数：同一批输入永远得到同一张核对单，晚到回执只是在输入侧追加后重算，
    因此更新的始终是同一张核对单而不是另起一份。
    """
    frames = OrderedDict()
    for row in packets:
        frame = int(row['frame'])
        if frame in frames:
            raise ValueError('PACKET_DUP_FRAME')
        frames[frame] = _blank_frame(row)

    # 同一回执重试只记账一次：receipt_id 去重，保留首次见到的内容
    seen, events = set(), []
    unknown_frames, duplicate_receipts = [], 0
    for row in receipts:
        receipt_id = row['receipt_id']
        if receipt_id in seen:
            duplicate_receipts += 1
            continue
        seen.add(receipt_id)
        events.append(row)
        frame = int(row['frame'])
        if frame not in frames:
            unknown_frames.append(frame)
            continue
        entry = frames[frame]
        entry['receipt_ids'].append(receipt_id)
        entry['device'] = row['device_id']
        entry['actual_hash'] = row.get('caption_hash') or None
        if row['status'] == 'NOT_PLAYED':
            entry['state'] = MISSED_CONFIRMED
        elif row['status'] == 'PLAYED':
            entry['state'] = (PLAYED_OK if entry['actual_hash'] == entry['expected_hash']
                              else WRONG_CAPTION)
        else:
            raise ValueError('RECEIPT_STATUS')
        if str(row.get('replay', '')).strip() in ('1', 'true', 'TRUE', 'True'):
            # 重放是事实标注：保留原核对状态，绝不冲掉别处漏播
            entry['replayed'] = 1

    summary = _summarize(frames.values())
    summary.update(duplicate_receipts=duplicate_receipts,
                   unknown_frames=sorted(set(unknown_frames)),
                   receipt_count=len(events),
                   packet_count=len({row['packet_id'] for row in packets}))
    return dict(frames=list(frames.values()), summary=summary, events=events)


def _summarize(entries):
    by_status = {status: 0 for status in STATUSES}
    by_cue = defaultdict(lambda: dict(signed=0, **{status: 0 for status in STATUSES}))
    by_packet = defaultdict(lambda: dict(signed=0, **{status: 0 for status in STATUSES}))
    for entry in entries:
        by_status[entry['state']] += 1
        if entry['replayed']:
            by_status[REPLAY] += 1
        for bucket, key in ((by_cue, entry['cue_id']), (by_packet, entry['packet_id'])):
            row = bucket[key]
            row['signed'] += 1
            row[entry['state']] += 1
            if entry['replayed']:
                row[REPLAY] += 1
    cues = [dict(cue_id=key, **row) for key, row in sorted(by_cue.items())]
    packets = [dict(packet_id=key, **row) for key, row in sorted(by_packet.items())]
    # 勾稽：各状态帧（重放不另占帧）相加必须等于签发包帧数
    signed = sum(by_status[status] for status in FRAME_STATES)
    return dict(signed_frames=signed, by_status=by_status, cues=cues, packets=packets,
                reconciled=(by_status[PENDING_RECEIPT] == 0),
                # 漏播只统计设备确认没播；回执未到不得误报为漏播
                missed_confirmed=by_status[MISSED_CONFIRMED],
                pending_receipt=by_status[PENDING_RECEIPT],
                wrong_caption=by_status[WRONG_CAPTION],
                replayed_frames=by_status[REPLAY])
