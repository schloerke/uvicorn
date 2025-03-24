from __future__ import annotations

from pathlib import Path
from socket import socket
from typing import Callable

from watchfiles import watch

from uvicorn.config import Config
from uvicorn.supervisors.basereload import BaseReload


class FileFilter:
    def __init__(self, config: Config):
        default_includes = ["*.py"]
        self.includes = [default for default in default_includes if default not in config.reload_excludes]
        self.includes.extend(config.reload_includes)
        self.includes = list(set(self.includes))

        default_excludes = [".*", ".py[cod]", ".sw.*", "~*"]
        self.excludes = [default for default in default_excludes if default not in config.reload_includes]
        self.excludes.extend(config.reload_excludes)
        self.excludes = list(set(self.excludes))

    def __call__(self, path: Path) -> bool:
        path_parts = path.parts

        for include_pattern in self.includes:
            if path.match(include_pattern):
                if str(path).endswith(include_pattern):
                    return True  # pragma: full coverage

                for exclude_pattern in self.excludes:
                    if exclude_pattern in path_parts or path.match(exclude_pattern):
                        return False # pragma: full coverage

                return True
        return False


class WatchFilesReload(BaseReload):
    def __init__(
        self,
        config: Config,
        target: Callable[[list[socket] | None], None],
        sockets: list[socket],
    ) -> None:
        super().__init__(config, target, sockets)
        self.reloader_name = "WatchFiles"
        self.reload_dirs = []
        for directory in config.reload_dirs:
            if Path.cwd() not in directory.parents:
                self.reload_dirs.append(directory)
        if Path.cwd() not in self.reload_dirs:
            self.reload_dirs.append(Path.cwd())

        self.watch_filter = FileFilter(config)
        self.watcher = watch(
            *self.reload_dirs,
            watch_filter=None,
            stop_event=self.should_exit,
            # using yield_on_timeout here mostly to make sure tests don't
            # hang forever, won't affect the class's behavior
            yield_on_timeout=True,
        )

    def should_restart(self) -> list[Path] | None:
        self.pause()

        changes = next(self.watcher)
        if changes:
            unique_paths = {Path(c[1]) for c in changes}
            return [p for p in unique_paths if self.watch_filter(p)]
        return None
