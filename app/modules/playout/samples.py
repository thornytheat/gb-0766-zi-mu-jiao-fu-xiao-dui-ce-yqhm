from app.problems import Rejection
from app.settings import SAMPLE_ROOT
from .parsing import parse_packets, parse_receipts
from .service import preview

PLAYOUT_SAMPLE = SAMPLE_ROOT / 'playout' / 'dirty'


def example_bundle(late=False):
    """样例核对单：默认只到首批回执；late=True 再并入晚到回执。"""
    packets = (PLAYOUT_SAMPLE / 'packets.csv').read_text(encoding='utf-8')
    receipts = (PLAYOUT_SAMPLE / 'receipts.csv').read_text(encoding='utf-8')
    if late:
        rows = parse_receipts(receipts) + parse_receipts(
            (PLAYOUT_SAMPLE / 'receipts_late.csv').read_text(encoding='utf-8'))
        from .ledger import build_ledger
        return build_ledger(parse_packets(packets), rows)
    return preview(packets, receipts)


def sample_text(name):
    if name not in ('packets', 'receipts', 'receipts_late'):
        raise Rejection('NO_SAMPLE', '找不到实播样例', 404)
    return (PLAYOUT_SAMPLE / f'{name}.csv').read_text(encoding='utf-8')
