from flask import Blueprint, jsonify, request
from app.problems import Rejection
from .parsing import parse_receipts
from .service import PlayoutStore, append_csv, preview, view

playout = Blueprint('playout', __name__, url_prefix='/api/playout')


def store():
    from flask import current_app
    return current_app.extensions['playout_store']


@playout.get('/<key>')
def ledger(key):
    return jsonify(view(store().open(key)))


@playout.post('/<key>/packets')
def packets(key):
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get('packets'), str):
        raise Rejection('PAYLOAD', '提交签发包 CSV 文本', 422)
    book = store().init(key, body['packets'])
    return jsonify(view(book)), 201


@playout.post('/<key>/receipts')
def receipts(key):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise Rejection('PAYLOAD', '提交回执 CSV 文本或单条回执', 422)
    if isinstance(body.get('receipts'), str):
        book, accepted, duplicates = append_csv(store(), key, body['receipts'])
    elif 'receipt_id' in body:
        book, accepted, duplicates = store().append(key, [body])
    else:
        raise Rejection('PAYLOAD', '提交回执 CSV 文本或单条回执', 422)
    result = view(book)
    result.update(accepted=accepted, duplicate_receipts=duplicates)
    return jsonify(result)


@playout.post('/preview')
def trial():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get('packets'), str):
        raise Rejection('PAYLOAD', '提交签发包 CSV 文本', 422)
    return jsonify(preview(body['packets'], body.get('receipts') or ''))
