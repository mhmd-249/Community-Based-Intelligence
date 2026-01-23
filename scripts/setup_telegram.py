#!/usr/bin/env python3
"""
Telegram Bot Setup Script

Configures the Telegram bot with webhooks and commands using the Bot API.

Usage:
    python scripts/setup_telegram.py --info
    python scripts/setup_telegram.py --set-webhook
    python scripts/setup_telegram.py --set-webhook --url https://example.com/webhooks/telegram
    python scripts/setup_telegram.py --delete-webhook
"""

import argparse
import asyncio
import sys
from typing import Any

import httpx

# Add project root to path for imports
sys.path.insert(0, str(__file__).rsplit("/scripts", 1)[0])

from cbi.config import get_settings

TELEGRAM_API_BASE = "https://api.telegram.org/bot"

# Bot commands to set
BOT_COMMANDS = [
    {"command": "start", "description": "Start reporting a health incident"},
    {"command": "help", "description": "Get help with using this bot"},
    {"command": "status", "description": "Check status of your recent report"},
]


class TelegramSetup:
    """Telegram bot setup and configuration."""

    def __init__(self, bot_token: str) -> None:
        self.bot_token = bot_token
        self.base_url = f"{TELEGRAM_API_BASE}{bot_token}"

    async def _request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a request to the Telegram Bot API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/{method}",
                json=params or {},
            )
            result = response.json()

            if not result.get("ok"):
                error_desc = result.get("description", "Unknown error")
                error_code = result.get("error_code", "N/A")
                raise Exception(f"Telegram API error [{error_code}]: {error_desc}")

            return result

    async def get_me(self) -> dict[str, Any]:
        """Get bot information."""
        result = await self._request("getMe")
        return result.get("result", {})

    async def get_webhook_info(self) -> dict[str, Any]:
        """Get current webhook configuration."""
        result = await self._request("getWebhookInfo")
        return result.get("result", {})

    async def set_webhook(
        self,
        url: str,
        secret_token: str | None = None,
        max_connections: int = 40,
        allowed_updates: list[str] | None = None,
    ) -> bool:
        """
        Set the webhook URL for receiving updates.

        Args:
            url: HTTPS URL to send updates to
            secret_token: Secret token for X-Telegram-Bot-Api-Secret-Token header
            max_connections: Maximum allowed simultaneous HTTPS connections
            allowed_updates: List of update types to receive

        Returns:
            True if successful
        """
        params: dict[str, Any] = {
            "url": url,
            "max_connections": max_connections,
        }

        if secret_token:
            params["secret_token"] = secret_token

        if allowed_updates:
            params["allowed_updates"] = allowed_updates
        else:
            # Only receive message updates for MVP
            params["allowed_updates"] = ["message"]

        await self._request("setWebhook", params)
        return True

    async def delete_webhook(self, drop_pending_updates: bool = False) -> bool:
        """
        Remove webhook integration.

        Args:
            drop_pending_updates: Pass True to drop all pending updates

        Returns:
            True if successful
        """
        params = {"drop_pending_updates": drop_pending_updates}
        await self._request("deleteWebhook", params)
        return True

    async def set_my_commands(
        self,
        commands: list[dict[str, str]],
    ) -> bool:
        """
        Set the bot's command list.

        Args:
            commands: List of command objects with 'command' and 'description'

        Returns:
            True if successful
        """
        await self._request("setMyCommands", {"commands": commands})
        return True


def print_header(text: str) -> None:
    """Print a formatted header."""
    print(f"\n{'=' * 50}")
    print(f"  {text}")
    print(f"{'=' * 50}\n")


def print_success(text: str) -> None:
    """Print success message."""
    print(f"[OK] {text}")


def print_error(text: str) -> None:
    """Print error message."""
    print(f"[ERROR] {text}")


def print_info(label: str, value: Any) -> None:
    """Print info line."""
    print(f"  {label}: {value}")


async def cmd_info(setup: TelegramSetup) -> None:
    """Display bot info and webhook status."""
    print_header("Bot Information")

    try:
        bot_info = await setup.get_me()
        print_info("Bot ID", bot_info.get("id"))
        print_info("Username", f"@{bot_info.get('username')}")
        print_info("Name", bot_info.get("first_name"))
        print_info("Can Join Groups", bot_info.get("can_join_groups", False))
        print_info(
            "Can Read Messages", bot_info.get("can_read_all_group_messages", False)
        )
        print_info("Supports Inline", bot_info.get("supports_inline_queries", False))
    except Exception as e:
        print_error(f"Failed to get bot info: {e}")
        return

    print_header("Webhook Status")

    try:
        webhook_info = await setup.get_webhook_info()
        url = webhook_info.get("url", "")
        print_info("URL", url if url else "(not set)")
        print_info("Has Custom Cert", webhook_info.get("has_custom_certificate", False))
        print_info("Pending Updates", webhook_info.get("pending_update_count", 0))
        print_info("Max Connections", webhook_info.get("max_connections", "N/A"))

        if webhook_info.get("last_error_date"):
            from datetime import UTC, datetime

            error_date = datetime.fromtimestamp(webhook_info["last_error_date"], tz=UTC)
            print_info("Last Error", webhook_info.get("last_error_message", "Unknown"))
            print_info("Error Time", error_date.isoformat())

        allowed = webhook_info.get("allowed_updates", [])
        print_info("Allowed Updates", ", ".join(allowed) if allowed else "(all)")
    except Exception as e:
        print_error(f"Failed to get webhook info: {e}")


async def cmd_set_webhook(
    setup: TelegramSetup,
    url: str,
    secret_token: str | None,
) -> None:
    """Set the webhook URL."""
    print_header("Setting Webhook")

    print_info("URL", url)
    print_info("Secret Token", "configured" if secret_token else "not set")

    try:
        await setup.set_webhook(url, secret_token)
        print_success("Webhook set successfully!")

        # Verify
        webhook_info = await setup.get_webhook_info()
        if webhook_info.get("url") == url:
            print_success("Webhook URL verified")
        else:
            print_error("Webhook URL mismatch after setting")
    except Exception as e:
        print_error(f"Failed to set webhook: {e}")
        return

    # Also set bot commands
    print_header("Setting Bot Commands")

    try:
        await setup.set_my_commands(BOT_COMMANDS)
        print_success("Bot commands set successfully!")
        for cmd in BOT_COMMANDS:
            print_info(f"/{cmd['command']}", cmd["description"])
    except Exception as e:
        print_error(f"Failed to set commands: {e}")


async def cmd_delete_webhook(setup: TelegramSetup, drop_pending: bool) -> None:
    """Delete the webhook."""
    print_header("Deleting Webhook")

    print_info("Drop Pending Updates", drop_pending)

    try:
        await setup.delete_webhook(drop_pending)
        print_success("Webhook deleted successfully!")
        print_info("Mode", "Polling mode enabled (use getUpdates)")
    except Exception as e:
        print_error(f"Failed to delete webhook: {e}")


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Telegram Bot Setup Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --info                    Show bot info and webhook status
  %(prog)s --set-webhook             Set webhook using TELEGRAM_WEBHOOK_URL env var
  %(prog)s --set-webhook --url URL   Set webhook to specific URL
  %(prog)s --delete-webhook          Remove webhook (switch to polling)
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--info",
        action="store_true",
        help="Display bot information and webhook status",
    )
    group.add_argument(
        "--set-webhook",
        action="store_true",
        help="Set the webhook URL",
    )
    group.add_argument(
        "--delete-webhook",
        action="store_true",
        help="Remove webhook (for polling mode)",
    )

    parser.add_argument(
        "--url",
        type=str,
        help="Webhook URL (overrides TELEGRAM_WEBHOOK_URL env var)",
    )
    parser.add_argument(
        "--drop-pending",
        action="store_true",
        help="Drop pending updates when deleting webhook",
    )

    args = parser.parse_args()

    # Load settings
    try:
        settings = get_settings()
        bot_token = settings.telegram_bot_token.get_secret_value()
    except Exception as e:
        print_error(f"Failed to load settings: {e}")
        print_info("Hint", "Make sure TELEGRAM_BOT_TOKEN is set in .env")
        sys.exit(1)

    setup = TelegramSetup(bot_token)

    if args.info:
        await cmd_info(setup)

    elif args.set_webhook:
        # Determine webhook URL
        webhook_url = args.url or settings.telegram_webhook_url
        if not webhook_url:
            print_error("No webhook URL provided")
            print_info("Hint", "Use --url or set TELEGRAM_WEBHOOK_URL in .env")
            sys.exit(1)

        # Get secret token if configured
        secret_token = None
        if settings.telegram_webhook_secret:
            secret_token = settings.telegram_webhook_secret.get_secret_value()

        await cmd_set_webhook(setup, webhook_url, secret_token)

    elif args.delete_webhook:
        await cmd_delete_webhook(setup, args.drop_pending)


if __name__ == "__main__":
    asyncio.run(main())
