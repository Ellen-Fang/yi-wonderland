"""牌陣、系統安全亂數洗牌與逐張抽牌規則。"""
import json
import secrets
from datetime import datetime, timezone
from uuid import uuid4
from app.config import ROOT
from app.errors import ApiError
from app.schemas.reading import CreateReading, DrawRequest

DECK = json.loads((ROOT / 'data/cards.json').read_text(encoding='utf-8-sig'))
SPREADS = json.loads((ROOT / 'data/spreads.json').read_text(encoding='utf-8-sig'))
CARDS = {card['id']: card for card in DECK}
if len(DECK) != 78 or len(CARDS) != 78:
    raise RuntimeError('牌組必須包含 78 張不重複的牌')


def shuffle_deck() -> list[dict]:
    cards = [{'cardId': card['id'], 'orientation': secrets.choice(('upright', 'reversed'))}
             for card in DECK]
    for i in range(len(cards) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        cards[i], cards[j] = cards[j], cards[i]
    return cards


def new_reading(body: CreateReading) -> dict:
    spread = next((item for item in SPREADS if item['id'] == body.spreadId), None)
    if spread is None:
        raise ApiError(400, 'INVALID_SPREAD', '請選擇有效的牌陣。')
    if spread.get('requiresOptions') and body.options is None:
        raise ApiError(400, 'INVALID_OPTIONS', '請填寫選項 A 與 B。')
    if not spread.get('requiresOptions') and body.options is not None:
        raise ApiError(400, 'INVALID_OPTIONS', '此牌陣不需要選項。')
    return {'id': str(uuid4()), 'question': body.question,
            'options': body.options.model_dump() if body.options else None,
            'spread': spread, 'deck': shuffle_deck(), 'cards': [], 'interpretation': None,
            'createdAt': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}


def public_reading(reading: dict) -> dict:
    count = len(reading['cards'])
    return {key: reading[key] for key in ('id', 'question', 'options', 'spread', 'cards', 'interpretation', 'createdAt')} | {
        'status': 'completed' if reading['interpretation'] else 'drawn' if count == 3 else 'drawing',
        'deckSize': 78, 'drawnCount': count, 'remainingDraws': 3 - count,
        'selectedPositions': [card['deckPosition'] for card in reading['cards']]}


def draw_card(reading: dict, body: DrawRequest) -> dict:
    if body.drawIndex < len(reading['cards']):
        if reading['cards'][body.drawIndex]['deckPosition'] != body.position:
            raise ApiError(409, 'DRAW_CONFLICT', '此個牌位已抽牌，請先同步結果。')
        return reading
    if body.drawIndex != len(reading['cards']):
        raise ApiError(409, 'DRAW_ORDER', '請依序抽第一、第二、第三張。')
    if any(card['deckPosition'] == body.position for card in reading['cards']):
        raise ApiError(409, 'POSITION_TAKEN', '這個位置已經抽過。')
    selected = reading['deck'][body.position]
    card = CARDS[selected['cardId']]
    reading['cards'].append(selected | {key: card[key] for key in ('nameZh', 'nameEn', 'image')} | {
        'deckPosition': body.position, 'position': reading['spread']['positions'][body.drawIndex]})
    return reading
