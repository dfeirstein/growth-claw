"""Workspace context loader — loads and caches .md files from ~/.growthclaw/.

Claude Code reads these files on every wake-up. The Python engine uses this
module to serve workspace context via MCP tools, so Claude Code can compose
messages with VOICE.md, SOUL.md, BUSINESS.md context.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from growthclaw.workspace import GROWTHCLAW_HOME

logger = logging.getLogger("growthclaw.workspace_context")

# Files loaded on every context refresh
CONTEXT_FILES = [
    "SOUL.md",
    "VOICE.md",
    "BUSINESS.md",
    "OWNER.md",
    "SECURITY.md",
    "COMPILER.md",
]

# Cache TTL in seconds (5 minutes)
_CACHE_TTL = 300


class WorkspaceContext:
    """Loads and caches workspace .md files for use by MCP tools and the engine.

    Usage:
        ctx = WorkspaceContext()
        voice = ctx.get("VOICE.md")
        all_context = ctx.get_all()
    """

    def __init__(self, workspace_dir: Path | None = None, cache_ttl: int = _CACHE_TTL) -> None:
        self._workspace = workspace_dir or GROWTHCLAW_HOME
        self._cache: dict[str, str] = {}
        self._skills_cache: dict[str, str] = {}
        self._last_loaded: float = 0.0
        self._cache_ttl = cache_ttl

    def _is_stale(self) -> bool:
        return (time.monotonic() - self._last_loaded) > self._cache_ttl

    def _load(self) -> None:
        """Load all context files from workspace."""
        self._cache.clear()
        self._skills_cache.clear()

        for filename in CONTEXT_FILES:
            path = self._workspace / filename
            if path.exists():
                try:
                    self._cache[filename] = path.read_text()
                except OSError as e:
                    logger.warning("Failed to read %s: %s", path, e)

        # Load skills
        skills_dir = self._workspace / "skills"
        if skills_dir.is_dir():
            for skill_file in skills_dir.glob("*.md"):
                try:
                    self._skills_cache[skill_file.name] = skill_file.read_text()
                except OSError as e:
                    logger.warning("Failed to read skill %s: %s", skill_file, e)

        self._last_loaded = time.monotonic()
        logger.info(
            "Workspace context loaded: %d files, %d skills",
            len(self._cache),
            len(self._skills_cache),
        )

    def _ensure_loaded(self) -> None:
        if not self._cache or self._is_stale():
            self._load()

    def get(self, filename: str) -> str | None:
        """Get content of a specific workspace file. Returns None if not found."""
        self._ensure_loaded()
        return self._cache.get(filename)

    def get_skill(self, skill_name: str) -> str | None:
        """Get content of a skill file. Accepts 'copywriter' or 'copywriter.md'."""
        self._ensure_loaded()
        if not skill_name.endswith(".md"):
            skill_name = f"{skill_name}.md"
        return self._skills_cache.get(skill_name)

    def get_all(self) -> dict[str, str]:
        """Get all loaded workspace context files."""
        self._ensure_loaded()
        return dict(self._cache)

    def get_all_skills(self) -> dict[str, str]:
        """Get all loaded skill files."""
        self._ensure_loaded()
        return dict(self._skills_cache)

    def get_composition_context(self) -> dict[str, Any]:
        """Get the context needed for message composition.

        Returns a dict with voice, soul, business, and owner content —
        the essential files Claude Code needs to compose personalized messages.
        """
        self._ensure_loaded()
        return {
            "voice": self._cache.get("VOICE.md", ""),
            "soul": self._cache.get("SOUL.md", ""),
            "business": self._cache.get("BUSINESS.md", ""),
            "owner": self._cache.get("OWNER.md", ""),
        }

    def invalidate(self) -> None:
        """Force a reload on next access."""
        self._last_loaded = 0.0

    @property
    def workspace_dir(self) -> Path:
        return self._workspace
