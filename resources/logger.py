from __future__ import annotations

import logging
import sys
from functools import lru_cache
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, cast

import structlog
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from structlog.processors import CallsiteParameter

if TYPE_CHECKING:
    from structlog.types import EventDict, Processor, WrappedLogger

type BoundLogger = structlog.stdlib.BoundLogger
type LogLevel = Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"]


class LoggingConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="LOG_",
        extra="forbid",
        frozen=True,
    )

    level: LogLevel = Field(default="INFO")
    json_output: bool = Field(default=False)
    service_name: str = Field(default="frost")
    file_path: str | None = Field(default=None)
    max_bytes: int = Field(default=50_000_000, ge=1024)
    backup_count: int = Field(default=10, ge=0)
    library_log_levels: dict[str, LogLevel] = Field(default_factory=dict)
    enable_otel: bool = Field(default=False)


class FormatterStrategy(Protocol):
    def build_processors(self, enable_otel: bool) -> list[Processor]: ...


class OutputStrategy(Protocol):
    def create_handler(self, config: LoggingConfig) -> logging.Handler: ...


def _add_otel_trace_context(
    _logger: WrappedLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    try:
        from opentelemetry import trace
    except ImportError:
        return event_dict

    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        span_context = current_span.get_span_context()
        event_dict["trace_id"] = format(span_context.trace_id, "032x")
        event_dict["span_id"] = format(span_context.span_id, "016x")

    return event_dict


class JsonFormatterStrategy:
    def build_processors(self, enable_otel: bool) -> list[Processor]:
        shared: list[Processor] = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    CallsiteParameter.FILENAME,
                    CallsiteParameter.LINENO,
                    CallsiteParameter.MODULE,
                ]
            ),
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
        ]

        if enable_otel:
            shared.append(_add_otel_trace_context)

        return [
            *shared,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]


class ConsoleFormatterStrategy:
    def build_processors(self, enable_otel: bool) -> list[Processor]:
        shared: list[Processor] = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    CallsiteParameter.FILENAME,
                    CallsiteParameter.LINENO,
                    CallsiteParameter.MODULE,
                ]
            ),
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
        ]

        if enable_otel:
            shared.append(_add_otel_trace_context)

        return [
            *shared,
            structlog.dev.ConsoleRenderer(),
        ]


class FileOutputStrategy:
    def create_handler(self, config: LoggingConfig) -> logging.Handler:
        if not config.file_path:
            raise ValueError("file_path required for FileOutputStrategy")

        log_path = Path(config.file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        handler = RotatingFileHandler(
            filename=str(log_path),
            maxBytes=config.max_bytes,
            backupCount=config.backup_count,
            encoding="utf-8",
        )
        handler.setLevel(config.level)
        handler.setFormatter(logging.Formatter("%(message)s"))

        return handler


class StreamOutputStrategy:
    def create_handler(self, config: LoggingConfig) -> logging.Handler:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(config.level)
        handler.setFormatter(logging.Formatter("%(message)s"))

        return handler


class LoggerFactory:
    @staticmethod
    def create(config: LoggingConfig) -> BoundLogger:
        formatter: FormatterStrategy = JsonFormatterStrategy() if config.json_output else ConsoleFormatterStrategy()

        processors = formatter.build_processors(config.enable_otel)

        structlog.configure(
            processors=processors,
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        output: OutputStrategy = FileOutputStrategy() if config.file_path else StreamOutputStrategy()

        handler = output.create_handler(config)

        root = logging.getLogger()
        root.handlers = [handler]
        root.setLevel(config.level)

        for lib_name, lib_level in config.library_log_levels.items():
            logging.getLogger(lib_name).setLevel(lib_level)

        structlog.contextvars.bind_contextvars(service=config.service_name)

        return cast(BoundLogger, structlog.get_logger())


@lru_cache(maxsize=1)
def _get_default_config() -> LoggingConfig:
    return LoggingConfig()


def configure_logging(config: LoggingConfig | None = None) -> None:
    actual_config = config if config is not None else _get_default_config()
    LoggerFactory.create(actual_config)


def get_logger(name: str | None = None) -> BoundLogger:
    return cast(BoundLogger, structlog.get_logger(name))


def bind_context(**kwargs: str | float | bool | None) -> None:
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    structlog.contextvars.clear_contextvars()
