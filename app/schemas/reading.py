"""輸入驗證、回傳格式；保留原有 camelCase API 欄位。"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.errors import ApiError


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Options(StrictModel):
    a: str = Field(min_length=1, max_length=300, strict=True)
    b: str = Field(min_length=1, max_length=300, strict=True)

    @field_validator('a', 'b', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class CreateReading(StrictModel):
    question: str = Field(min_length=1, max_length=100, strict=True)
    spreadId: str = Field(strict=True)
    options: Options | None = None

    @field_validator('question', mode='before')
    @classmethod
    def question_limit(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if len(value) > 100:
                raise ApiError(400, 'QUESTION_TOO_LONG', '問題最多 100 字（含標點與空白），請精簡後再送出。')
        return value


class DrawRequest(StrictModel):
    position: int = Field(ge=0, le=77, strict=True)
    drawIndex: int = Field(ge=0, le=2, strict=True)


class Position(StrictModel):
    id: str
    label: str
    meaning: str


class Spread(StrictModel):
    id: str
    name: str
    description: str
    positions: list[Position]
    requiresOptions: bool = False


class DrawnCard(StrictModel):
    cardId: str
    nameZh: str
    nameEn: str
    image: str
    orientation: Literal['upright', 'reversed']
    deckPosition: int
    position: Position


class CardInterpretation(StrictModel):
    positionId: str
    cardId: str
    interpretation: str


class Interpretation(StrictModel):
    summary: str
    cards: list[CardInterpretation] = Field(min_length=3, max_length=3)
    advice: list[str] = Field(min_length=1, max_length=5)
    reflection: str

    @model_validator(mode='after')
    def content_is_present(self):
        # 深度由 prompt 引導；有效回覆不因未達指定字數而失敗。
        texts = [self.summary, self.reflection, *self.advice,
                 *(card.interpretation for card in self.cards)]
        if any(not item.strip() for item in texts):
            raise ValueError('內容不可空白')
        return self


class ReadingResponse(StrictModel):
    id: str
    question: str
    options: Options | None
    spread: Spread
    status: Literal['drawing', 'drawn', 'completed']
    deckSize: int
    drawnCount: int
    remainingDraws: int
    selectedPositions: list[int]
    cards: list[DrawnCard]
    interpretation: Interpretation | None
    createdAt: str


class CreatedReadingResponse(ReadingResponse):
    accessToken: str
