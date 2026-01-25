# services/encryption.py
"""
Encryption service for securing sensitive credentials at rest.

Uses Fernet symmetric encryption with guild-specific salts.
The master key is stored in environment variables, while
per-guild salts are stored in the database.

This provides:
- At-rest encryption for RCON passwords, API keys, etc.
- Guild isolation (each guild's credentials are encrypted with a unique derived key)
- Key rotation support
"""

import base64
import hashlib
import logging
import os
import secrets
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """Base exception for encryption errors."""
    pass


class EncryptionKeyError(EncryptionError):
    """Encryption key not configured or invalid."""
    pass


class DecryptionError(EncryptionError):
    """Failed to decrypt data."""
    pass


class EncryptionService:
    """
    Handles encryption and decryption of sensitive data.

    Uses a master key from environment combined with per-guild salts
    to create unique encryption keys per guild.
    """

    def __init__(self, master_key: Optional[str] = None):
        """
        Initialize encryption service.

        Args:
            master_key: Master encryption key. If not provided, reads from
                       ENCRYPTION_MASTER_KEY via settings or environment.
        """
        # Try to get key from multiple sources
        if master_key:
            self._master_key = master_key
        else:
            # First try importing from settings (uses python-decouple)
            try:
                from config.settings import ENCRYPTION_MASTER_KEY
                self._master_key = ENCRYPTION_MASTER_KEY
            except ImportError:
                self._master_key = None

            # Fall back to direct environment variable
            if not self._master_key:
                self._master_key = os.environ.get('ENCRYPTION_MASTER_KEY')

        if not self._master_key:
            logger.warning("ENCRYPTION_MASTER_KEY not set - using generated key (not persistent!)")
            self._master_key = Fernet.generate_key().decode()

        # Validate key format
        try:
            # If it's a valid Fernet key, use it directly
            Fernet(self._master_key.encode() if isinstance(self._master_key, str) else self._master_key)
            self._master_key_bytes = self._master_key.encode() if isinstance(self._master_key, str) else self._master_key
        except Exception:
            # Otherwise, derive a key from it
            self._master_key_bytes = self._derive_key_from_password(self._master_key, b'master_salt')

        self._fernet_cache: dict[int, Fernet] = {}  # guild_id -> Fernet instance

    def _derive_key_from_password(self, password: str, salt: bytes) -> bytes:
        """Derive a Fernet-compatible key from a password and salt."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,  # OWASP recommended minimum
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key

    def generate_guild_salt(self) -> bytes:
        """Generate a new random salt for a guild."""
        return secrets.token_bytes(32)

    def get_guild_fernet(self, guild_id: int, guild_salt: bytes) -> Fernet:
        """
        Get or create a Fernet instance for a guild.

        Args:
            guild_id: The guild ID
            guild_salt: The guild's unique salt from database

        Returns:
            Fernet instance for encrypting/decrypting guild data
        """
        if guild_id not in self._fernet_cache:
            # Derive guild-specific key from master key + guild salt
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=guild_salt,
                iterations=100000,
            )
            guild_key = base64.urlsafe_b64encode(kdf.derive(self._master_key_bytes))
            self._fernet_cache[guild_id] = Fernet(guild_key)

        return self._fernet_cache[guild_id]

    def clear_cache(self, guild_id: Optional[int] = None) -> None:
        """
        Clear cached Fernet instances.

        Args:
            guild_id: If provided, only clear cache for this guild.
                     If None, clear all cached instances.
        """
        if guild_id is not None:
            self._fernet_cache.pop(guild_id, None)
        else:
            self._fernet_cache.clear()

    def encrypt(self, plaintext: str, guild_id: int, guild_salt: bytes) -> bytes:
        """
        Encrypt a plaintext string.

        Args:
            plaintext: The string to encrypt
            guild_id: The guild ID for key derivation
            guild_salt: The guild's salt from database

        Returns:
            Encrypted bytes (can be stored in VARBINARY column)
        """
        try:
            fernet = self.get_guild_fernet(guild_id, guild_salt)
            return fernet.encrypt(plaintext.encode())
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise EncryptionError(f"Failed to encrypt data: {e}")

    def decrypt(self, ciphertext: bytes, guild_id: int, guild_salt: bytes) -> str:
        """
        Decrypt encrypted bytes to plaintext string.

        Args:
            ciphertext: The encrypted bytes
            guild_id: The guild ID for key derivation
            guild_salt: The guild's salt from database

        Returns:
            Decrypted plaintext string
        """
        try:
            fernet = self.get_guild_fernet(guild_id, guild_salt)
            return fernet.decrypt(ciphertext).decode()
        except InvalidToken:
            logger.error("Decryption failed: Invalid token (wrong key or corrupted data)")
            raise DecryptionError("Failed to decrypt: Invalid token")
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise DecryptionError(f"Failed to decrypt data: {e}")

    def rotate_guild_key(self, guild_id: int, old_salt: bytes, new_salt: bytes,
                         encrypted_values: list[bytes]) -> list[bytes]:
        """
        Rotate encryption key for a guild by re-encrypting all values.

        Args:
            guild_id: The guild ID
            old_salt: The old guild salt
            new_salt: The new guild salt
            encrypted_values: List of currently encrypted values

        Returns:
            List of re-encrypted values with the new key
        """
        # Get old and new Fernet instances
        old_fernet = self.get_guild_fernet(guild_id, old_salt)

        # Clear cache to get new fernet with new salt
        self.clear_cache(guild_id)
        new_fernet = self.get_guild_fernet(guild_id, new_salt)

        # Re-encrypt all values
        re_encrypted = []
        for ciphertext in encrypted_values:
            try:
                plaintext = old_fernet.decrypt(ciphertext)
                re_encrypted.append(new_fernet.encrypt(plaintext))
            except Exception as e:
                logger.error(f"Failed to rotate encryption for value: {e}")
                raise EncryptionError(f"Key rotation failed: {e}")

        return re_encrypted


# Singleton instance
_encryption_service: Optional[EncryptionService] = None


def get_encryption_service() -> EncryptionService:
    """Get the singleton encryption service instance."""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service


def reset_encryption_service() -> None:
    """Reset the singleton to force re-initialization."""
    global _encryption_service
    _encryption_service = None


def initialize_encryption() -> bool:
    """
    Initialize encryption service and verify the key is valid.
    Call this early in bot startup to ensure encryption is properly configured.

    Returns:
        True if encryption is configured with a persistent key, False if using generated key
    """
    global _encryption_service
    reset_encryption_service()
    service = get_encryption_service()

    # Check if we're using a real key or generated one
    try:
        from config.settings import ENCRYPTION_MASTER_KEY
        if ENCRYPTION_MASTER_KEY:
            logger.info("Encryption initialized with master key from settings")
            return True
    except ImportError:
        pass

    if os.environ.get('ENCRYPTION_MASTER_KEY'):
        logger.info("Encryption initialized with master key from environment")
        return True

    logger.warning("Encryption using non-persistent generated key!")
    return False


def encrypt_credential(plaintext: str, guild_id: int, guild_salt: bytes) -> bytes:
    """Convenience function to encrypt a credential."""
    return get_encryption_service().encrypt(plaintext, guild_id, guild_salt)


def decrypt_credential(ciphertext: bytes, guild_id: int, guild_salt: bytes) -> str:
    """Convenience function to decrypt a credential."""
    return get_encryption_service().decrypt(ciphertext, guild_id, guild_salt)


def generate_salt() -> bytes:
    """Convenience function to generate a new guild salt."""
    return get_encryption_service().generate_guild_salt()
