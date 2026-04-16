# -*- coding: utf-8 -*-
"""
Photo processing state machine with valid transitions.
照片处理状态机 - 管理照片生命周期中的合法状态转换.

State transitions:
    PENDING
      --> DOWNLOADING  (start download)
      --> FAILED        (pre-check error)
    DOWNLOADING
      --> DOWNLOADED   (success)
      --> SKIPPED       (duplicate hash)
      --> FAILED        (network error / invalid URL)
    DOWNLOADED
      --> PREPROCESSING (start preprocess)
      --> FAILED        (file corrupt)
    PREPROCESSING
      --> RECOGNIZING  (start recognition)
      --> FAILED        (image format error)
    RECOGNIZING
      --> RECOGNIZED    (done, may or may not contain target)
      --> FAILED        (API error)
    RECOGNIZED
      --> STORING       (contains target -> store)
      --> COMPLETED     (no target -> skip storage)
      --> FAILED        (unexpected error)
    STORING
      --> STORED        (saved locally)
      --> UPLOADING     (auto-upload enabled)
      --> FAILED        (disk full / permission error)
    STORED
      --> UPLOADING     (start personal album upload)
    UPLOADING
      --> UPLOADED      (upload success)
      --> FAILED        (upload error)
    UPLOADED
      --> COMPLETED     (final state)
    COMPLETED           (terminal state)
    FAILED              (terminal state, can retry -> DOWNLOADING)
    SKIPPED             (terminal state)

Retry policy:
    FAILED --(if retry_count < max_retries)--> DOWNLOADING
"""

import logging
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from app.models.photo import PhotoStatus

logger = logging.getLogger(__name__)


class TransitionError(Exception):
    """Invalid state transition attempted."""

    def __init__(
        self,
        from_state: PhotoStatus,
        to_state: PhotoStatus,
        message: str = "",
    ):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid transition {from_state.value} "
            f"-> {to_state.value}: {message}"
        )


class PhotoStateMachine:
    """
    Validates and tracks photo lifecycle state transitions.

    Usage:
        sm = PhotoStateMachine()
        sm.transition(photo_id="abc", current=PhotoStatus.PENDING,
                      next=PhotoStatus.DOWNLOADING)  # OK
        sm.transition(photo_id="abc", current=PhotoStatus.PENDING,
                      next=PhotoStatus.COMPLETED)  # raises TransitionError
    """

    # Define valid transitions as frozen sets for O(1) lookup
    _TRANSITIONS: Dict[PhotoStatus, FrozenSet[PhotoStatus]] = {
        # Initial states
        PhotoStatus.PENDING: frozenset({
            PhotoStatus.DOWNLOADING, PhotoStatus.FAILED,
        }),
        PhotoStatus.DOWNLOADING: frozenset({
            PhotoStatus.DOWNLOADED, PhotoStatus.SKIPPED,
            PhotoStatus.FAILED,
        }),
        PhotoStatus.DOWNLOADED: frozenset({
            PhotoStatus.PREPROCESSING, PhotoStatus.FAILED,
        }),
        PhotoStatus.PREPROCESSING: frozenset({
            PhotoStatus.RECOGNIZING, PhotoStatus.FAILED,
        }),
        PhotoStatus.RECOGNIZING: frozenset({
            PhotoStatus.RECOGNIZED, PhotoStatus.FAILED,
        }),
        # Post-recognition branching
        PhotoStatus.RECOGNIZED: frozenset({
            PhotoStatus.STORING, PhotoStatus.COMPLETED,
            PhotoStatus.FAILED,
        }),
        PhotoStatus.STORING: frozenset({
            PhotoStatus.STORED, PhotoStatus.UPLOADING,
            PhotoStatus.FAILED,
        }),
        PhotoStatus.STORED: frozenset({
            PhotoStatus.UPLOADING, PhotoStatus.COMPLETED,
            PhotoStatus.FAILED,
        }),
        PhotoStatus.UPLOADING: frozenset({
            PhotoStatus.UPLOADED, PhotoStatus.FAILED,
        }),
        PhotoStatus.UPLOADED: frozenset({PhotoStatus.COMPLETED}),
        # Terminal states
        PhotoStatus.COMPLETED: frozenset(),
        PhotoStatus.FAILED: frozenset(),  # Retry via external mechanism
        PhotoStatus.SKIPPED: frozenset(),
    }

    TERMINAL_STATES: Set[PhotoStatus] = {
        PhotoStatus.COMPLETED,
        PhotoStatus.SKIPPED,
    }

    RETRYABLE_STATES: Set[PhotoStatus] = {
        PhotoStatus.FAILED,
    }

    MAX_RETRIES: int = 3

    def __init__(self):
        pass

    @classmethod
    def is_valid_transition(
        cls,
        from_state: PhotoStatus,
        to_state: PhotoStatus,
    ) -> bool:
        """Check if a transition is allowed."""
        allowed = cls._TRANSITIONS.get(from_state, frozenset())
        return to_state in allowed

    @classmethod
    def get_allowed_next(
        cls, from_state: PhotoStatus,
    ) -> List[PhotoStatus]:
        """List all valid target states from a given state."""
        return sorted(
            cls._TRANSITIONS.get(from_state, frozenset()),
            key=lambda s: s.value,
        )

    @classmethod
    def transition(
        cls,
        photo_id: str,
        current: PhotoStatus,
        to_state: PhotoStatus,
        reason: str = "",
    ) -> None:
        """
        Attempt a validated state transition.

        Raises:
            TransitionError: If transition is not allowed.
        """
        if not cls.is_valid_transition(current, to_state):
            raise TransitionError(current, to_state, reason)

        logger.debug(
            "State transition %s: %s -> %s%s",
            photo_id,
            current.value,
            to_state.value,
            f" ({reason})" if reason else "",
        )

    @classmethod
    def can_retry(
        cls, status: PhotoStatus, retry_count: int,
    ) -> bool:
        """Check if a photo in the given status can be retried."""
        if status not in cls.RETRYABLE_STATES:
            return False
        if retry_count >= cls.MAX_RETRIES:
            logger.debug(
                "Max retries (%d) exceeded for retry",
                cls.MAX_RETRIES,
            )
            return False
        return True

    @classmethod
    def get_retry_target(cls, status: PhotoStatus) -> Optional[PhotoStatus]:
        """
        Get the target state when retrying a failed photo.
        Returns the appropriate starting state based on where it failed.
        """
        retry_map: Dict[PhotoStatus, PhotoStatus] = {
            PhotoStatus.FAILED: PhotoStatus.DOWNLOADING,
        }
        return retry_map.get(status)
