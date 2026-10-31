"""Shared exception types. Each carries a message that is safe to show to the user."""

from __future__ import annotations


class StudioError(Exception):
    """Base class. ``user_message`` is shown in the UI; technical detail goes to the log."""

    default_message = "Something went wrong."

    def __init__(self, user_message: str | None = None) -> None:
        self.user_message = user_message or self.default_message
        super().__init__(self.user_message)


class ConfigurationError(StudioError):
    default_message = "The studio is not configured correctly."


class ModelError(StudioError):
    default_message = "The AI model request failed."


class ModelResponseError(ModelError):
    default_message = "The AI model returned a response that could not be used."


class DiscoveryError(StudioError):
    default_message = "The website could not be analysed."


class GenerationError(StudioError):
    default_message = "Generation failed."


class GitHubError(StudioError):
    default_message = "The GitHub request failed."


class ExecutionError(StudioError):
    default_message = "The test execution failed to start."


class NotFoundError(StudioError):
    default_message = "That item does not exist or belongs to another browser."
