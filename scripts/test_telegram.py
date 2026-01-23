#!/usr/bin/env python3
"""
Telegram Gateway Test Script

Tests the Telegram messaging gateway by sending messages.

Usage:
    python scripts/test_telegram.py --chat-id 12345 --message "Hello, world!"
    python scripts/test_telegram.py --chat-id 12345  # Interactive mode
    python scripts/test_telegram.py --chat-id 12345 --template welcome
"""

import argparse
import asyncio
import sys

# Add project root to path for imports
sys.path.insert(0, str(__file__).rsplit("/scripts", 1)[0])

from cbi.config import get_settings
from cbi.services.messaging import (
    MessagingAuthenticationError,
    MessagingError,
    MessagingRateLimitError,
    MessagingSendError,
    OutgoingMessage,
    TelegramGateway,
)


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


def print_info(label: str, value: str) -> None:
    """Print info line."""
    print(f"  {label}: {value}")


async def send_message(
    gateway: TelegramGateway,
    chat_id: str,
    text: str,
) -> bool:
    """
    Send a message using the gateway.

    Args:
        gateway: TelegramGateway instance
        chat_id: Target chat ID
        text: Message text

    Returns:
        True if successful, False otherwise
    """
    message = OutgoingMessage(chat_id=chat_id, text=text)

    try:
        message_id = await gateway.send_message(message)
        print_success(f"Message sent! ID: {message_id}")
        return True
    except MessagingAuthenticationError as e:
        print_error(f"Authentication failed: {e.message}")
        print_info("Hint", "Check your TELEGRAM_BOT_TOKEN")
        return False
    except MessagingRateLimitError as e:
        print_error(f"Rate limited: {e.message}")
        if e.retry_after:
            print_info("Retry After", f"{e.retry_after} seconds")
        return False
    except MessagingSendError as e:
        print_error(f"Send failed: {e.message}")
        if e.status_code:
            print_info("Status Code", str(e.status_code))
        return False
    except MessagingError as e:
        print_error(f"Messaging error: {e.message}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False


async def send_template(
    gateway: TelegramGateway,
    chat_id: str,
    template_name: str,
    params: dict[str, str] | None = None,
) -> bool:
    """
    Send a template message using the gateway.

    Args:
        gateway: TelegramGateway instance
        chat_id: Target chat ID
        template_name: Name of the template
        params: Template parameters

    Returns:
        True if successful, False otherwise
    """
    try:
        message_id = await gateway.send_template(chat_id, template_name, params)
        print_success(f"Template sent! ID: {message_id}")
        return True
    except Exception as e:
        print_error(f"Failed to send template: {e}")
        return False


async def interactive_mode(gateway: TelegramGateway, chat_id: str) -> None:
    """
    Interactive mode for sending multiple messages.

    Args:
        gateway: TelegramGateway instance
        chat_id: Target chat ID
    """
    print_header("Interactive Mode")
    print("Type messages to send. Commands:")
    print("  /quit - Exit interactive mode")
    print("  /template <name> - Send a template")
    print()

    while True:
        try:
            text = input("Message> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break

        if not text:
            continue

        if text == "/quit":
            print("Goodbye!")
            break

        if text.startswith("/template "):
            template_name = text.split(" ", 1)[1].strip()
            await send_template(gateway, chat_id, template_name)
        else:
            await send_message(gateway, chat_id, text)


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Telegram Gateway Test Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --chat-id 12345 --message "Hello!"
  %(prog)s --chat-id 12345 --template welcome
  %(prog)s --chat-id 12345  # Interactive mode

To find your chat ID:
  1. Message your bot on Telegram
  2. Visit: https://api.telegram.org/bot<TOKEN>/getUpdates
  3. Look for "chat":{"id": YOUR_CHAT_ID}
        """,
    )

    parser.add_argument(
        "--chat-id",
        type=str,
        required=True,
        help="Telegram chat ID to send message to",
    )
    parser.add_argument(
        "--message",
        "-m",
        type=str,
        help="Message text to send",
    )
    parser.add_argument(
        "--template",
        "-t",
        type=str,
        help="Template name to send (e.g., welcome, welcome_ar)",
    )
    parser.add_argument(
        "--list-templates",
        action="store_true",
        help="List available templates",
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

    # Create gateway
    gateway = TelegramGateway(bot_token=bot_token)

    try:
        print_header("Telegram Gateway Test")
        print_info("Chat ID", args.chat_id)

        if args.list_templates:
            print_header("Available Templates")
            # Access the gateway's templates
            for name in gateway._templates:
                preview = gateway._templates[name][:50]
                print_info(name, f"{preview}...")
            return

        if args.template:
            print_info("Template", args.template)
            success = await send_template(gateway, args.chat_id, args.template)
            sys.exit(0 if success else 1)

        if args.message:
            print_info(
                "Message",
                args.message[:50] + "..." if len(args.message) > 50 else args.message,
            )
            success = await send_message(gateway, args.chat_id, args.message)
            sys.exit(0 if success else 1)

        # No message or template specified, enter interactive mode
        await interactive_mode(gateway, args.chat_id)

    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
