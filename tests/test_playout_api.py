from app.modules.playout.samples import sample_text
from app.modules.playout.service import view


def _packets():
    return sample_text('packets')


def test_balance_page_renders_playout_sample(client):
    html = client.get('/sheet/balance?sample=dirty').get_data(as_text=True)
    assert '实播回执核对' in html
    assert '确认没播' in html and '回执未到' in html and '倒回重放' in html
    assert 'play-state' in html


def test_preview_api(client):
    response = client.post('/api/playout/preview', json={
        'packets': _packets(), 'receipts': sample_text('receipts')})
    assert response.status_code == 200
    body = response.json
    assert body['summary']['missed_confirmed'] == 3
    assert body['summary']['wrong_caption'] == 1
    assert body['summary']['pending_receipt'] == 6
    assert body['summary']['replayed_frames'] == 2


def test_full_late_receipt_flow(client, saved):
    key = saved['id']
    # 建档前查不到核对单
    assert client.get(f'/api/playout/{key}').status_code == 404
    created = client.post(f'/api/playout/{key}/packets', json={'packets': _packets()})
    assert created.status_code == 201
    # 重复建档被拒绝
    assert client.post(f'/api/playout/{key}/packets', json={'packets': _packets()}).status_code == 409

    first = client.post(f'/api/playout/{key}/receipts',
                        json={'receipts': sample_text('receipts')}).json
    assert first['accepted'] == 18 and first['duplicate_receipts'] == 1
    assert first['summary']['pending_receipt'] == 6

    # 晚到回执：同一核对单更新，重试回执再次去重
    late = client.post(f'/api/playout/{key}/receipts',
                       json={'receipts': sample_text('receipts_late')}).json
    assert late['run_id'] == key
    assert late['accepted'] == 6 and late['duplicate_receipts'] == 1
    assert late['summary']['reconciled'] is True
    assert late['summary']['pending_receipt'] == 0
    # 漏播不被重放/补报抵销
    assert late['summary']['missed_confirmed'] == 3

    final = client.get(f'/api/playout/{key}').json
    # 持久化账目中同号回执只留一条（累计两次重试都没入账）
    stored = client.application.extensions['playout_store'].open(key)['receipts']
    assert len(stored) == len({r['receipt_id'] for r in stored}) == 24
    assert final['summary']['duplicate_receipts'] == 0
    assert view(client.application.extensions['playout_store'].open(key))['summary'] == final['summary']


def test_single_receipt_endpoint_and_unknown_frame(client, saved):
    key = saved['id']
    client.post(f'/api/playout/{key}/packets', json={'packets': _packets()})
    ok = client.post(f'/api/playout/{key}/receipts', json={
        'receipt_id': 'R-721', 'device_id': 'SCREEN-A', 'frame': '721', 'status': 'PLAYED',
        'caption_hash': next(
            r['caption_hash'] for r in client.application.extensions['playout_store']
            .open(key)['packets'] if r['frame'] == 721),
        'received_at': '2026-11-24T12:00:00+00:00', 'replay': ''})
    assert ok.status_code == 200 and ok.json['accepted'] == 1
    bad = client.post(f'/api/playout/{key}/receipts', json={
        'receipt_id': 'RX', 'device_id': 'SCREEN-A', 'frame': '9999', 'status': 'NOT_PLAYED',
        'caption_hash': '', 'received_at': '2026-11-24T12:00:00+00:00', 'replay': ''})
    assert bad.status_code == 422 and bad.json['code'] == 'RECEIPT_UNKNOWN_FRAME'


def test_balance_page_uses_archived_playbook(client, saved):
    key = saved['id']
    client.post(f'/api/playout/{key}/packets', json={'packets': _packets()})
    client.post(f'/api/playout/{key}/receipts', json={'receipts': sample_text('receipts')})
    html = client.get(f'/sheet/balance?run={key}').get_data(as_text=True)
    assert '补录回执' in html and '核对单' in html


def test_bad_payloads(client, saved):
    key = saved['id']
    assert client.post(f'/api/playout/{key}/packets', json={}).status_code == 422
    assert client.post('/api/playout/preview', json={'packets': 'not,a,csv\n1,2,3\n'}).status_code == 422
