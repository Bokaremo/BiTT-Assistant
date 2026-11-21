"""BiTT Assistant - مساعد معلم التقنية · Bokaremo IT Tools."""

__version__ = "0.1.0"
APP_NAME = "BiTT Assistant"
APP_NAME_AR = "مساعد معلم التقنية"

# Explicit submodule imports so PyInstaller's dependency scanner
# always collects every module in the biit package.
from . import config, naming, drives, roster, sections, treegen, deploy, reports, maintenance, foldericon, protection, projectforms, studentcards  # noqa: E402, F401
