from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BrowserConfig:
    engine: str = "chromium"
    headless: bool = False
    profile_dir: Path = Path(".browser/profile")
    artifact_dir: Path = Path(".browser/artifacts")
    upload_dir: Path = Path(".browser/uploads")
    action_timeout: float = 15
    navigation_timeout: float = 30
    script_timeout: float = 60

    def __post_init__(self) -> None:
        if self.engine not in {"chromium", "firefox", "webkit"}:
            raise ValueError("BROWSER_ENGINE must be chromium, firefox, or webkit")
        for name in ("action_timeout", "navigation_timeout", "script_timeout"):
            if not 0 < getattr(self, name) <= 600:
                raise ValueError(f"{name} must be between zero and 600 seconds")

    @classmethod
    def from_env(cls) -> BrowserConfig:
        return cls(
            engine=os.getenv("BROWSER_ENGINE", "chromium"),
            headless=os.getenv("BROWSER_HEADLESS", "false").lower() == "true",
            profile_dir=Path(os.getenv("BROWSER_PROFILE_DIR", ".browser/profile")),
            artifact_dir=Path(os.getenv("BROWSER_ARTIFACT_DIR", ".browser/artifacts")),
            upload_dir=Path(os.getenv("BROWSER_UPLOAD_DIR", ".browser/uploads")),
            action_timeout=float(os.getenv("BROWSER_ACTION_TIMEOUT", "15")),
            navigation_timeout=float(os.getenv("BROWSER_NAVIGATION_TIMEOUT", "30")),
            script_timeout=float(os.getenv("BROWSER_SCRIPT_TIMEOUT", "60")),
        )

    def wire(self) -> dict:
        return {
            **self.__dict__,
            **{
                name: str(getattr(self, name).resolve())
                for name in ("profile_dir", "artifact_dir", "upload_dir")
            },
        }
