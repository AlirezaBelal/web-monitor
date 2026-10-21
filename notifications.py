"""Notification backends for WebMonitor.

Secrets are resolved from environment variables at runtime and are never written
to tracked configuration or health/state files.
"""

from __future__ import annotations

import os
from typing import Mapping, Optional

import requests

from web_monitor import ConfigurationError, MonitorConfig, validate_http_url


class NotificationDeliveryError(RuntimeError):
    """Raised when a configured notification backend cannot deliver an alert."""


class WebhookNotifier:
    """Deliver a minimal change event to a generic HTTP webhook."""

    def __init__(
        self,
        url: str,
        target_name: str,
        timeout_seconds: float,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.url = validate_http_url(url, "webhook URL")
        self.target_name = target_name
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def __call__(self, title: str, message: str) -> None:
        payload = {
            "event": "webmonitor.change",
            "target": self.target_name,
            "title": title,
            "message": message,
        }
        try:
            response = self.session.post(
                self.url,
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise NotificationDeliveryError(
                "Webhook notification delivery failed"
            ) from exc


class TelegramNotifier:
    """Deliver an alert through the Telegram Bot API."""

    API_ROOT = "https://api.telegram.org"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        target_name: str,
        timeout_seconds: float,
        session: Optional[requests.Session] = None,
    ) -> None:
        token = bot_token.strip()
        if not token:
            raise ConfigurationError("Telegram bot token environment variable is empty")
        self._url = f"{self.API_ROOT}/bot{token}/sendMessage"
        self.chat_id = chat_id.strip()
        if not self.chat_id:
            raise ConfigurationError("Telegram chat ID environment variable is empty")
        self.target_name = target_name
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def __call__(self, title: str, message: str) -> None:
        text = f"[{self.target_name}] {title}\n{message}"
        try:
            response = self.session.post(
                self._url,
                json={"chat_id": self.chat_id, "text": text},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            # Never include the request URL because it contains the bot token.
            raise NotificationDeliveryError(
                "Telegram notification delivery failed"
            ) from exc


def build_notifier(
    config: MonitorConfig,
    *,
    desktop_override: bool = False,
    show_name: bool = False,
    environ: Optional[Mapping[str, str]] = None,
    session: Optional[requests.Session] = None,
):
    """Build the configured notifier without exposing environment secret values."""
    environment = os.environ if environ is None else environ
    backend = "desktop" if desktop_override else config.notification_backend
    prefix = f"[{config.name}] " if show_name else ""

    if backend == "console":
        return lambda title, message: print(f"{prefix}{title}: {message}")

    if backend == "desktop":
        try:
            from plyer import notification
        except ImportError as exc:
            raise ConfigurationError(
                "Desktop notifications require requirements-desktop.txt"
            ) from exc

        def desktop_notifier(title: str, message: str) -> None:
            desktop_title = f"{config.name}: {title}" if show_name else title
            try:
                notification.notify(
                    title=desktop_title,
                    message=message,
                    timeout=10,
                )
            except Exception as exc:
                raise NotificationDeliveryError(
                    "Desktop notification delivery failed"
                ) from exc

        return desktop_notifier

    if backend == "webhook":
        url = _required_environment_value(environment, config.webhook_url_env)
        return WebhookNotifier(
            url=url,
            target_name=config.name,
            timeout_seconds=config.notification_timeout_seconds,
            session=session,
        )

    if backend == "telegram":
        token = _required_environment_value(environment, config.telegram_token_env)
        chat_id = _required_environment_value(environment, config.telegram_chat_id_env)
        return TelegramNotifier(
            bot_token=token,
            chat_id=chat_id,
            target_name=config.name,
            timeout_seconds=config.notification_timeout_seconds,
            session=session,
        )

    raise ConfigurationError("Unsupported notification backend")


def _required_environment_value(
    environment: Mapping[str, str],
    variable_name: str,
) -> str:
    value = environment.get(variable_name, "").strip()
    if not value:
        raise ConfigurationError(
            f"Required notification environment variable is not set: {variable_name}"
        )
    return value
