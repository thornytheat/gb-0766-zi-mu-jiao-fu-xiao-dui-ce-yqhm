import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from app.digests import encode
from app.problems import Rejection
from .ledger import build_ledger
from .parsing import parse_packets, parse_receipts, validate_receipt

KEY = re.compile('[0-9a-f]{64}')


class PlayoutStore:
    """按归档档号保存核对单（签发包 + 已采信回执）。

    与不可变的签发证据分文件存放：核对单要随晚到回执原地更新。
    """

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key):
        if not KEY.fullmatch(key):
            raise Rejection('NO_RUN', '交付档案不存在', 404)
        return self.root / f'{key}.playbook.json'

    def open(self, key):
        try:
            return json.loads(self._path(key).read_bytes())
        except FileNotFoundError as error:
            raise Rejection('NO_PLAYBOOK', '该档号还没有实播核对单', 404) from error

    def save(self, book):
        path = self._path(book['run_id'])
        with NamedTemporaryFile(dir=self.root, prefix='.play-', delete=False) as draft:
            tmp = Path(draft.name)
            try:
                draft.write(encode(book))
                draft.flush()
                os.fsync(draft.fileno())
                os.replace(tmp, path)
            finally:
                tmp.unlink(missing_ok=True)

    def init(self, key, packets_text):
        path = self._path(key)
        if path.exists():
            raise Rejection('PLAYBOOK_EXISTS', '核对单已建立，不能重复签发', 409)
        packets = parse_packets(packets_text)
        now = datetime.now(timezone.utc).isoformat()
        book = dict(run_id=key, packets=packets, receipts=[], created_at=now, updated_at=now)
        self.save(book)
        return book

    def append(self, key, receipts):
        book = self.open(key)
        known = {row['receipt_id'] for row in book['receipts']}
        signed_frames = {row['frame'] for row in book['packets']}
        accepted, duplicates = [], 0
        for row in receipts:
            data = validate_receipt(row)
            if data['receipt_id'] in known:
                # 同一回执重试：不重复记账
                duplicates += 1
                continue
            if data['frame'] not in signed_frames:
                raise Rejection('RECEIPT_UNKNOWN_FRAME', f"帧 {data['frame']} 不在签发包内", 422)
            known.add(data['receipt_id'])
            accepted.append(data)
        if accepted:
            book['receipts'].extend(accepted)
            # 晚到回执补齐后更新原核对单：档号不变，只刷新时间与账
            book['updated_at'] = datetime.now(timezone.utc).isoformat()
            self.save(book)
        return book, len(accepted), duplicates


def view(book):
    ledger = build_ledger(book['packets'], book['receipts'])
    return dict(run_id=book['run_id'], created_at=book['created_at'],
                updated_at=book['updated_at'], **ledger)


def preview(packets_text, receipts_text=''):
    packets = parse_packets(packets_text)
    receipts = parse_receipts(receipts_text) if receipts_text else []
    return build_ledger(packets, receipts)


def append_csv(store, key, csv_text):
    return store.append(key, parse_receipts(csv_text))
