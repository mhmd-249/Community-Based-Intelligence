"""
Redis-based state management service for conversation state.

Handles storage, retrieval, and lifecycle management of ConversationState
in Redis with appropriate TTLs and session management.
"""

import hashlib
import json
import uuid
from datetime import date, datetime
from typing import Any

import redis.asyncio as aioredis

from cbi.agents.state import ConversationState, create_initial_state
from cbi.config import get_logger, get_settings

logger = get_logger(__name__)

# Redis key prefixes
CONVERSATION_KEY_PREFIX = "cbi:conversation:"
SESSION_KEY_PREFIX = "cbi:session:"

# TTL constants (in seconds)
DEFAULT_STATE_TTL = 24 * 60 * 60  # 24 hours
DEFAULT_SESSION_TTL = 60 * 60  # 1 hour


class StateServiceError(Exception):
    """Base exception for state service errors."""

    pass


class StateNotFoundError(StateServiceError):
    """Raised when a conversation state is not found."""

    pass


class StateService:
    """
    Manages conversation state in Redis.

    Provides methods for creating, retrieving, updating, and deleting
    conversation state with automatic session management.

    Key patterns:
    - conversation:{conversation_id} -> Full ConversationState JSON
    - session:{platform}:{phone_hash} -> conversation_id

    Example:
        >>> service = StateService()
        >>> await service.initialize()
        >>> state, is_new = await service.get_or_create_conversation("telegram", "+249123456789")
        >>> if is_new:
        ...     print("Started new conversation")
        >>> await service.save_state(state)
    """

    def __init__(
        self,
        redis_client: aioredis.Redis | None = None,
        state_ttl: int = DEFAULT_STATE_TTL,
        session_ttl: int = DEFAULT_SESSION_TTL,
    ) -> None:
        """
        Initialize the StateService.

        Args:
            redis_client: Optional pre-configured Redis client.
                         If not provided, will create one on initialize().
            state_ttl: TTL for conversation state in seconds (default: 24 hours)
            session_ttl: TTL for session mapping in seconds (default: 1 hour)
        """
        self._redis: aioredis.Redis | None = redis_client
        self._state_ttl = state_ttl
        self._session_ttl = session_ttl
        self._settings = get_settings()
        self._initialized = redis_client is not None

    async def initialize(self) -> None:
        """
        Initialize the Redis connection if not already connected.

        Should be called before using the service if no redis_client
        was provided in __init__.
        """
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._settings.redis_url.get_secret_value(),
                encoding="utf-8",
                decode_responses=True,
            )
            self._initialized = True
            logger.info("StateService initialized with Redis connection")

    async def close(self) -> None:
        """Close the Redis connection if we own it."""
        if self._redis is not None and self._initialized:
            await self._redis.close()
            self._redis = None
            self._initialized = False
            logger.info("StateService Redis connection closed")

    @property
    def redis(self) -> aioredis.Redis:
        """Get the Redis client, raising if not initialized."""
        if self._redis is None:
            raise StateServiceError(
                "StateService not initialized. Call initialize() first."
            )
        return self._redis

    def _phone_hash(self, phone: str) -> str:
        """
        Create a truncated SHA-256 hash of a phone number for key efficiency.

        Args:
            phone: Phone number to hash

        Returns:
            16-character hex hash string
        """
        salt = self._settings.phone_hash_salt.get_secret_value()
        data = f"{salt}{phone}".encode()
        full_hash = hashlib.sha256(data).hexdigest()
        return full_hash[:16]

    def _conversation_key(self, conversation_id: str) -> str:
        """Generate Redis key for conversation state."""
        return f"{CONVERSATION_KEY_PREFIX}{conversation_id}"

    def _session_key(self, platform: str, phone_hash: str) -> str:
        """Generate Redis key for session mapping."""
        return f"{SESSION_KEY_PREFIX}{platform}:{phone_hash}"

    def _generate_conversation_id(self) -> str:
        """Generate a unique conversation ID."""
        return f"conv_{uuid.uuid4().hex[:16]}"

    @staticmethod
    def _json_encoder(obj: Any) -> Any:
        """Custom JSON encoder for datetime and date objects."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    def _serialize_state(self, state: ConversationState) -> str:
        """Serialize ConversationState to JSON string."""
        return json.dumps(dict(state), default=self._json_encoder)

    def _deserialize_state(self, data: str) -> ConversationState:
        """Deserialize JSON string to ConversationState."""
        parsed = json.loads(data)
        return ConversationState(**parsed)

    async def get_or_create_conversation(
        self,
        platform: str,
        phone: str,
    ) -> tuple[ConversationState, bool]:
        """
        Get existing conversation or create a new one.

        Checks for an existing session by platform and phone hash.
        If found, loads and returns the existing state.
        If not found, creates a new conversation with initial state.

        Args:
            platform: Messaging platform (telegram/whatsapp)
            phone: Reporter's phone number

        Returns:
            Tuple of (ConversationState, is_new) where is_new indicates
            whether a new conversation was created.

        Raises:
            StateServiceError: If Redis operation fails
        """
        phone_hash = self._phone_hash(phone)
        session_key = self._session_key(platform, phone_hash)

        try:
            # Check for existing session
            existing_conversation_id = await self.redis.get(session_key)

            if existing_conversation_id:
                # Try to load existing state
                state = await self.get_state(existing_conversation_id)
                if state is not None:
                    # Extend session TTL on access
                    await self.redis.expire(session_key, self._session_ttl)
                    logger.debug(
                        "Resumed existing conversation",
                        conversation_id=existing_conversation_id,
                        platform=platform,
                    )
                    return state, False

            # Create new conversation
            conversation_id = self._generate_conversation_id()
            state = create_initial_state(conversation_id, phone, platform)

            # Save state and create session mapping
            await self._save_state_internal(state, phone_hash)

            logger.info(
                "Created new conversation",
                conversation_id=conversation_id,
                platform=platform,
            )

            return state, True

        except aioredis.RedisError as e:
            logger.error(
                "Redis error in get_or_create_conversation",
                error=str(e),
                platform=platform,
            )
            raise StateServiceError(f"Failed to get or create conversation: {e}") from e

    async def get_state(self, conversation_id: str) -> ConversationState | None:
        """
        Load conversation state from Redis.

        Args:
            conversation_id: The conversation ID to load

        Returns:
            ConversationState if found, None otherwise

        Raises:
            StateServiceError: If Redis operation fails (other than not found)
        """
        key = self._conversation_key(conversation_id)

        try:
            data = await self.redis.get(key)

            if data is None:
                logger.debug(
                    "Conversation state not found",
                    conversation_id=conversation_id,
                )
                return None

            state = self._deserialize_state(data)
            logger.debug(
                "Loaded conversation state",
                conversation_id=conversation_id,
                mode=state.get("current_mode"),
            )
            return state

        except json.JSONDecodeError as e:
            logger.error(
                "Failed to deserialize conversation state",
                conversation_id=conversation_id,
                error=str(e),
            )
            raise StateServiceError(f"Invalid state data for {conversation_id}") from e
        except aioredis.RedisError as e:
            logger.error(
                "Redis error loading state",
                conversation_id=conversation_id,
                error=str(e),
            )
            raise StateServiceError(f"Failed to load state: {e}") from e

    async def _save_state_internal(
        self,
        state: ConversationState,
        phone_hash: str | None = None,
    ) -> None:
        """
        Internal method to save state with optional session creation.

        Args:
            state: ConversationState to save
            phone_hash: If provided, creates/extends session mapping
        """
        conversation_id = state["conversation_id"]
        platform = state["platform"]
        conv_key = self._conversation_key(conversation_id)

        # Serialize and save state with TTL
        data = self._serialize_state(state)
        await self.redis.setex(conv_key, self._state_ttl, data)

        # Create or extend session mapping if phone_hash provided
        if phone_hash:
            session_key = self._session_key(platform, phone_hash)
            await self.redis.setex(session_key, self._session_ttl, conversation_id)

    async def save_state(self, state: ConversationState) -> None:
        """
        Save conversation state to Redis.

        Also extends the session TTL for the associated phone/platform.

        Args:
            state: ConversationState to save

        Raises:
            StateServiceError: If Redis operation fails
        """
        conversation_id = state["conversation_id"]
        reporter_phone = state["reporter_phone"]

        try:
            phone_hash = self._phone_hash(reporter_phone)
            await self._save_state_internal(state, phone_hash)

            logger.debug(
                "Saved conversation state",
                conversation_id=conversation_id,
                mode=state.get("current_mode"),
                turn_count=state.get("turn_count"),
            )

        except aioredis.RedisError as e:
            logger.error(
                "Redis error saving state",
                conversation_id=conversation_id,
                error=str(e),
            )
            raise StateServiceError(f"Failed to save state: {e}") from e

    async def delete_state(self, conversation_id: str) -> bool:
        """
        Delete conversation state and associated session.

        Args:
            conversation_id: The conversation ID to delete

        Returns:
            True if state was deleted, False if not found

        Raises:
            StateServiceError: If Redis operation fails
        """
        try:
            # First load the state to get phone and platform for session cleanup
            state = await self.get_state(conversation_id)

            if state is None:
                return False

            # Build keys to delete
            conv_key = self._conversation_key(conversation_id)
            phone_hash = self._phone_hash(state["reporter_phone"])
            session_key = self._session_key(state["platform"], phone_hash)

            # Delete both keys
            deleted = await self.redis.delete(conv_key, session_key)

            logger.info(
                "Deleted conversation state",
                conversation_id=conversation_id,
                keys_deleted=deleted,
            )

            return deleted > 0

        except aioredis.RedisError as e:
            logger.error(
                "Redis error deleting state",
                conversation_id=conversation_id,
                error=str(e),
            )
            raise StateServiceError(f"Failed to delete state: {e}") from e

    async def extend_session(self, platform: str, phone: str) -> bool:
        """
        Extend the session TTL for active conversation.

        Useful for keeping a conversation active during long pauses.

        Args:
            platform: Messaging platform
            phone: Reporter's phone number

        Returns:
            True if session was extended, False if session not found

        Raises:
            StateServiceError: If Redis operation fails
        """
        phone_hash = self._phone_hash(phone)
        session_key = self._session_key(platform, phone_hash)

        try:
            # Check if session exists
            exists = await self.redis.exists(session_key)

            if not exists:
                logger.debug(
                    "Session not found for extension",
                    platform=platform,
                )
                return False

            # Extend TTL
            await self.redis.expire(session_key, self._session_ttl)

            logger.debug(
                "Extended session TTL",
                platform=platform,
                ttl_seconds=self._session_ttl,
            )

            return True

        except aioredis.RedisError as e:
            logger.error(
                "Redis error extending session",
                platform=platform,
                error=str(e),
            )
            raise StateServiceError(f"Failed to extend session: {e}") from e

    async def get_active_conversation_count(self) -> int:
        """
        Get the count of active conversations in Redis.

        Returns:
            Number of active conversation states
        """
        try:
            pattern = f"{CONVERSATION_KEY_PREFIX}*"
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)
            return len(keys)
        except aioredis.RedisError as e:
            logger.error("Redis error counting conversations", error=str(e))
            return 0

    async def get_session_info(
        self,
        platform: str,
        phone: str,
    ) -> dict[str, Any] | None:
        """
        Get information about an active session.

        Args:
            platform: Messaging platform
            phone: Reporter's phone number

        Returns:
            Dict with session info or None if no session exists
        """
        phone_hash = self._phone_hash(phone)
        session_key = self._session_key(platform, phone_hash)

        try:
            conversation_id = await self.redis.get(session_key)

            if conversation_id is None:
                return None

            ttl = await self.redis.ttl(session_key)
            state = await self.get_state(conversation_id)

            return {
                "conversation_id": conversation_id,
                "platform": platform,
                "session_ttl_remaining": ttl,
                "current_mode": state.get("current_mode") if state else None,
                "turn_count": state.get("turn_count") if state else None,
            }

        except aioredis.RedisError as e:
            logger.error("Redis error getting session info", error=str(e))
            return None


# Singleton instance for convenience
_state_service: StateService | None = None


async def get_state_service() -> StateService:
    """
    Get or create the StateService singleton.

    Returns:
        Initialized StateService instance
    """
    global _state_service

    if _state_service is None:
        _state_service = StateService()
        await _state_service.initialize()

    return _state_service


async def close_state_service() -> None:
    """Close the StateService singleton if it exists."""
    global _state_service

    if _state_service is not None:
        await _state_service.close()
        _state_service = None
