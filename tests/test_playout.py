import hashlib

import pytest

from app.modules.playout.ledger import (
    MISSED_CONFIRMED, PENDING_RECEIPT, PLAYED_OK, REPLAY, WRONG_CAPTION, build_ledger,
)
from app.modules.playout.parsing import parse_packets, parse_receipts
from app.modules.playout.samples import example_bundle
from app.modules.playout.service import PlayoutStore, preview, view
from app.problems import Rejection


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()[:12]


PACKETS_CSV = (
    'packet_id,device_id,frame,cue_id,track,caption_text,caption_hash\n'
    'P1,DEV,10,C1,简中,甲,{h1}\n'
    'P1,DEV,11,C1,简中,甲,{h1}\n'
    'P1,DEV,12,C1,简中,甲,{h1}\n'
    'P2,DEV,20,C2,简中,乙,{h2}\n'
    'P2,DEV,21,C2,简中,乙,{h2}\n'
).format(h1=digest('甲'), h2=digest('乙'))


def test_pending_receipt_not_false_missed():
    """设备断线没回执是 PENDING_RECEIPT，不能误报漏播。"""
    result = preview(PACKETS_CSV)
    states = {row['frame']: row['state'] for row in result['frames']}
    assert states == {10: PENDING_RECEIPT, 11: PENDING_RECEIPT, 12: PENDING_RECEIPT,
                      20: PENDING_RECEIPT, 21: PENDING_RECEIPT}
    assert result['summary']['missed_confirmed'] == 0
    assert result['summary']['pending_receipt'] == 5
    assert result['summary']['reconciled'] is False


def test_confirmed_missed_distinct_from_pending():
    """设备确认没播与未收到回执分两类。"""
    receipts = (
        'receipt_id,device_id,frame,status,caption_hash,received_at,replay\n'
        f'R1,DEV,10,NOT_PLAYED,,2026-11-24T12:00:00+00:00,\n'
        f'R2,DEV,11,PLAYED,{digest("甲")},2026-11-24T12:00:01+00:00,\n'
    )
    result = preview(PACKETS_CSV, receipts)
    states = {row['frame']: row['state'] for row in result['frames']}
    assert states[10] == MISSED_CONFIRMED
    assert states[11] == PLAYED_OK
    assert states[12] == PENDING_RECEIPT
    assert result['summary']['missed_confirmed'] == 1
    assert result['summary']['pending_receipt'] == 3


def test_wrong_caption_listed_separately():
    """播够帧数但放错字幕，单列 WRONG_CAPTION，不与漏播混淆。"""
    receipts = (
        'receipt_id,device_id,frame,status,caption_hash,received_at,replay\n'
        f'R1,DEV,10,PLAYED,{digest("别的字幕")},2026-11-24T12:00:00+00:00,\n'
    )
    result = preview(PACKETS_CSV, receipts)
    row = next(row for row in result['frames'] if row['frame'] == 10)
    assert row['state'] == WRONG_CAPTION
    assert result['summary']['wrong_caption'] == 1
    assert result['summary']['missed_confirmed'] == 0


def test_replay_never_offsets_missed_elsewhere():
    """倒回重放只标注；别处确认没播仍计入漏播，不被抵销。"""
    receipts = (
        'receipt_id,device_id,frame,status,caption_hash,received_at,replay\n'
        f'R1,DEV,10,NOT_PLAYED,,2026-11-24T12:00:00+00:00,\n'
        f'R2,DEV,20,PLAYED,{digest("乙")},2026-11-24T12:05:00+00:00,1\n'
        f'R3,DEV,21,PLAYED,{digest("乙")},2026-11-24T12:05:01+00:00,1\n'
    )
    result = preview(PACKETS_CSV, receipts)
    missed = next(row for row in result['frames'] if row['frame'] == 10)
    replayed = [row for row in result['frames'] if row['replayed']]
    assert missed['state'] == MISSED_CONFIRMED
    assert {row['frame'] for row in replayed} == {20, 21}
    assert all(row['state'] == PLAYED_OK for row in replayed)
    assert result['summary']['missed_confirmed'] == 1
    assert result['summary']['replayed_frames'] == 2
    # 帧守恒：状态帧之和等于签发帧，重放不另占帧
    by = result['summary']['by_status']
    assert sum(by[name] for name in (PLAYED_OK, WRONG_CAPTION, MISSED_CONFIRMED, PENDING_RECEIPT)) == 5


def test_duplicate_receipt_id_counted_once():
    """同一回执重试（相同 receipt_id）不重复记账。"""
    line = f'R1,DEV,11,PLAYED,{digest("甲")},2026-11-24T12:00:00+00:00,\n'
    receipts = ('receipt_id,device_id,frame,status,caption_hash,received_at,replay\n'
                + line * 3)
    result = preview(PACKETS_CSV, receipts)
    row = next(row for row in result['frames'] if row['frame'] == 11)
    assert row['receipt_ids'] == ['R1']
    assert result['summary']['duplicate_receipts'] == 2
    assert result['summary']['receipt_count'] == 1
    assert result['summary']['by_status'][PLAYED_OK] == 1


def test_late_receipt_updates_same_sheet(tmp_path):
    """晚到回执补齐后更新同一张核对单（档号不变，未到转已核对）。"""
    store = PlayoutStore(tmp_path)
    key = 'a' * 64
    store.init(key, PACKETS_CSV)
    first = view(store.open(key))
    assert first['summary']['pending_receipt'] == 5
    created = first['created_at']

    book, accepted, duplicates = store.append(key, parse_receipts(
        'receipt_id,device_id,frame,status,caption_hash,received_at,replay\n'
        f'R1,DEV,11,PLAYED,{digest("甲")},2026-11-24T12:00:00+00:00,\n'))
    assert (accepted, duplicates) == (1, 0)
    second = view(book)
    assert second['run_id'] == key
    assert second['updated_at'] >= created
    assert second['summary']['pending_receipt'] == 4
    assert second['summary']['by_status'][PLAYED_OK] == 1
    # 存储里仍是同一档号、同一份核对单
    assert store.open(key)['run_id'] == key


def test_store_retry_dedup_and_unknown_frame(tmp_path):
    store = PlayoutStore(tmp_path)
    key = 'b' * 64
    store.init(key, PACKETS_CSV)
    row = dict(receipt_id='R9', device_id='DEV', frame='12', status='NOT_PLAYED',
               caption_hash='', received_at='2026-11-24T12:00:00+00:00', replay='')
    store.append(key, [row])
    _, accepted, duplicates = store.append(key, [dict(row)])  # 同号重试
    assert (accepted, duplicates) == (0, 1)
    with pytest.raises(Rejection, match='签发包'):
        store.append(key, [dict(row, receipt_id='RX', frame='999')])
    # 上一条整体拒收，不留下半截账
    assert {r['receipt_id'] for r in store.open(key)['receipts']} == {'R9'}


def test_sample_bundle_story():
    first = example_bundle()
    late = example_bundle(late=True)
    assert first['summary']['pending_receipt'] == 6 and not first['summary']['reconciled']
    assert late['summary']['pending_receipt'] == 0 and late['summary']['reconciled']
    # 晚到批次里 R-721 第三次出现，依旧不重复记账；漏播与重放口径不变
    assert late['summary']['duplicate_receipts'] == 2
    assert late['summary']['missed_confirmed'] == first['summary']['missed_confirmed'] == 3
    assert late['summary']['wrong_caption'] == 1
    assert late['summary']['replayed_frames'] == 2


def test_packet_hash_self_check():
    bad = PACKETS_CSV.replace(digest('甲'), digest('假'))
    with pytest.raises(Rejection, match='签发包'):
        parse_packets(bad)


def test_receipt_validation():
    with pytest.raises(Rejection, match='PLAYED'):
        parse_receipts(
            'receipt_id,device_id,frame,status,caption_hash,received_at,replay\n'
            'R1,DEV,10,PLAYED,,2026-11-24T12:00:00+00:00,\n')
    with pytest.raises(Rejection, match='状态'):
        parse_receipts(
            'receipt_id,device_id,frame,status,caption_hash,received_at,replay\n'
            'R1,DEV,10,MAYBE,,2026-11-24T12:00:00+00:00,\n')


def test_duplicate_packet_frame_rejected():
    dup = PACKETS_CSV + f'P3,DEV,10,C3,简中,丙,{digest("丙")}\n'
    with pytest.raises(Rejection, match='签发包'):
        parse_packets(dup)


def test_engine_rejects_duplicate_signed_frame():
    packets = parse_packets(PACKETS_CSV)
    with pytest.raises(ValueError, match='PACKET_DUP_FRAME'):
        build_ledger(packets + [packets[0]], [])


def test_replay_flag_truthy_variants():
    for flag in ('1', 'true', 'TRUE'):
        rows = parse_receipts(
            'receipt_id,device_id,frame,status,caption_hash,received_at,replay\n'
            f'R1,DEV,11,PLAYED,{digest("甲")},2026-11-24T12:00:00+00:00,{flag}\n')
        assert rows[0]['replay'] == '1'


def test_bom_tolerated():
    rows = parse_packets('﻿' + PACKETS_CSV)
    assert len(rows) == 5
