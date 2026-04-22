"""설정 API용 Pydantic 모델 (main에서 라우트 등록 시 사용)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SettingsPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    telegram_bot_token: str = Field("", alias="telegramBotToken")
    telegram_chat_id: str = Field("", alias="telegramChatId")
    openai_api_key: str = Field("", alias="openaiApiKey")
    telegram_notifications_enabled: bool = Field(True, alias="telegram_realtime_enabled")
    telegram_alert_threshold_percent: float = Field(25.0, alias="telegram_alert_threshold_percent")
    telegram_min_expected_profit_krw: int = Field(0, alias="telegramMinExpectedProfitKrw")
    threshold: float = Field(25.0, alias="threshold")
    require_warranty: bool = Field(True, alias="requireWarranty")
    min_grade: str = Field("B", alias="minGrade")
    selected_brands: list[str] = Field(default_factory=list, alias="selectedBrands")
    selected_categories: list[str] = Field(default_factory=list, alias="selectedCategoryIds")


class TelegramTestPayload(BaseModel):
    """비어 있으면 서버에 저장된 값으로 테스트."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    telegram_bot_token: str | None = Field(default=None, alias="telegramBotToken")
    telegram_chat_id: str | None = Field(default=None, alias="telegramChatId")
