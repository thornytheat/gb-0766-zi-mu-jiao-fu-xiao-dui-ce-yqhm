import csv
import hashlib
from io import StringIO
from app.problems import Rejection

BOM = '\ufeff'
PACKET_FIELDS = ('packet_id', 'device_id', 'frame', 'cue_id', 'track', 'caption_text', 'caption_hash')
RECEIPT_FIELDS = ('receipt_id', 'device_id', 'frame', 'status', 'caption_hash', 'received_at', 'replay')
RECEIPT_STATUSES = ('PLAYED', 'NOT_PLAYED')
REPLAY_TRUTHY = {'1', 'true', 'TRUE', 'True'}


def _read(text, fields, name):
    try:
        reader = csv.DictReader(StringIO(text.removeprefix(BOM), newline=''))
    except csv.Error as exc:
        raise Rejection('CSV', f'{name} CSV 损坏') from exc
    if reader.fieldnames is None:
        raise Rejection('EMPTY', f'{name}文件为空')
    if set(reader.fieldnames) != set(fields) or len(reader.fieldnames) != len(fields):
        raise Rejection('HEADER', f'{name}表头不符，需要 {",".join(fields)}')
    rows = []
    try:
        for raw in reader:
            line = reader.line_num + 1
            if not any((value or '').strip() for value in raw.values()):
                continue
            rows.append(dict(line=line, **{key: (raw.get(key) or '').strip() for key in fields}))
    except csv.Error as exc:
        raise Rejection('CSV', f'{name} CSV 损坏') from exc
    if not rows:
        raise Rejection('HEADER_ONLY', f'{name}仅含表头')
    return rows


def parse_packets(text):
    rows, bad, frames = _read(text, PACKET_FIELDS, '签发包'), [], set()
    for row in rows:
        missing = [key for key in ('packet_id', 'device_id', 'frame', 'cue_id', 'track', 'caption_hash')
                   if not row[key]]
        if missing:
            bad.append(dict(row, code='MISSING'))
        elif not row['frame'].isdigit():
            bad.append(dict(row, code='FRAME_LABEL'))
        elif int(row['frame']) in frames:
            bad.append(dict(row, code='PACKET_DUP_FRAME'))
        elif row['caption_text'] and hashlib.sha256(
                row['caption_text'].encode()).hexdigest()[:12] != row['caption_hash']:
            bad.append(dict(row, code='PACKET_HASH_MISMATCH'))
        else:
            row['frame'] = int(row['frame'])
            frames.add(row['frame'])
    if bad:
        raise Rejection('PACKET_INVALID', '签发包存在无法采信的帧行', 422)
    return rows


def validate_receipt(row):
    """校验单条回执（dict），返回规范化行；非法时抛 Rejection。"""
    data = {key: str(row.get(key) or '').strip() for key in RECEIPT_FIELDS}
    if not all(data[key] for key in ('receipt_id', 'device_id', 'frame', 'status', 'received_at')):
        raise Rejection('RECEIPT_INVALID', '回执必填字段缺失', 422)
    if not data['frame'].isdigit():
        raise Rejection('RECEIPT_INVALID', '回执帧号无效', 422)
    if data['status'] not in RECEIPT_STATUSES:
        raise Rejection('RECEIPT_STATUS', '回执状态只能是 PLAYED 或 NOT_PLAYED', 422)
    if data['status'] == 'PLAYED' and not data['caption_hash']:
        raise Rejection('RECEIPT_NO_HASH', 'PLAYED 回执必须带字幕指纹', 422)
    if data['replay'] and data['replay'] not in REPLAY_TRUTHY:
        raise Rejection('REPLAY_FLAG', '重放标记只能取 1/true', 422)
    data['frame'] = int(data['frame'])
    data['replay'] = '1' if data['replay'] in REPLAY_TRUTHY else ''
    return data


def parse_receipts(text):
    return [validate_receipt(row) for row in _read(text, RECEIPT_FIELDS, '回执')]
