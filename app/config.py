"""Provide settings at the start of the backend setup flow.

The setup checker creates this class before opening a connection.
Later phases can use the same settings without duplicating configuration.
No settings instance is created when this module is imported.

The person running the application supplies the real .env file.
The repository supplies only .env.example with placeholders.
Environment variables can override the file for local tooling.
Commands should run from the repository root to find that file.

Database credentials belong only to trusted backend code.
The database URL contains a password, so it is also a secret.
Supabase keys stay wrapped even when settings are inspected.
The Google key is reserved for later answer generation.
The Hugging Face token allows access to the configured model.

SecretStr redacts ordinary string and JSON representations.
Code must unwrap a secret only when a library needs its value.
Never pass an unwrapped value to a print or logging call.
Validation errors hide their input values for the same reason.

Local embeddings are the only implemented provider in this phase.
The model identifier comes directly from the project plan.
The fixed dimension matches the migration's vector column.
A different dimension must fail before data can be ingested.

The chat model identifier is configuration for a later phase.
This module does not load models or make API requests.
It does not connect to Postgres or apply SQL migrations.
Extra environment entries are ignored to keep configuration focused.

Offline tests disable dotenv loading and supply dummy settings.
Live setup checks are run manually after the SQL files are applied.
"""

from decimal import Decimal
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Validation errors can otherwise include the original credential input.
        hide_input_in_errors=True,
    )

    database_url: SecretStr
    supabase_url: str
    supabase_anon_key: SecretStr
    supabase_service_role_key: SecretStr
    google_api_key: SecretStr
    hf_token: SecretStr

    embedding_provider: Literal["local", "gemini"] = "local"
    embedding_model: str = "google/embeddinggemma-2"
    embedding_dim: int = 768
    chat_model: str = "google_genai:gemini-3.5-flash-lite"
    max_output_tokens: int = Field(default=800, gt=0)
    allowed_email_domain: str = "dxb.manipal.edu"
    questions_per_day: int = Field(default=5, gt=0)
    max_context_tokens: int = Field(default=4000, gt=0)
    global_daily_cap: int = Field(default=100, gt=0)
    global_daily_budget_usd: Decimal | None = Field(default=None, gt=0)
    price_input_per_1m_usd: Decimal = Field(default=Decimal("0"), ge=0)
    price_output_per_1m_usd: Decimal = Field(default=Decimal("0"), ge=0)

    @field_validator("global_daily_budget_usd", mode="before")
    @classmethod
    def empty_budget_is_disabled(cls, value):
        return None if value == "" else value

    @field_validator("embedding_dim")
    @classmethod
    def validate_embedding_dim(cls, value: int) -> int:
        # Validate after integer parsing so environment strings work too.
        if value != 768:
            raise ValueError("embedding_dim must be 768 to match the database schema")
        return value
