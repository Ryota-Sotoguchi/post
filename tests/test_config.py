from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import fields
from pathlib import Path
from unittest.mock import patch

from mbti_tiktok_bot.config import load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_uses_neutral_default_hashtags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            with patch.dict(os.environ, {}, clear=True):
                config = load_config(root)

        self.assertEqual(config.default_hashtags, ["#MBTI", "#mbti診断", "#16personalities", "#性格診断"])

    def test_load_config_reads_only_venv_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".venv").mkdir(parents=True, exist_ok=True)
            (root / ".env").write_text(
                "PHONE_EXPORT_AUTO=false\nMBTI_IMAGES_DIR=root_images\n",
                encoding="utf-8",
            )
            (root / ".venv" / ".env").write_text(
                "PHONE_EXPORT_AUTO=true\nMBTI_IMAGES_DIR=venv_images\nDEFAULT_HASHTAGS=#One #Two\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                config = load_config(root)

        self.assertTrue(config.phone_export_auto)
        self.assertEqual(config.official_images_dir, root / "venv_images")
        self.assertEqual(config.default_hashtags, ["#One", "#Two"])

    def test_load_config_reads_generation_settings(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DAILY_POSTS": "5",
                "MBTI_IMAGES_DIR": "custom_images",
                "DEFAULT_HASHTAGS": "#Alpha #Beta",
                "TOPIC_DEPTH": "standard",
                "PHONE_EXPORT_AUTO": "true",
                "PHONE_EXPORT_DIR": "sync_out",
            },
            clear=False,
        ):
            config = load_config(Path.cwd())

        self.assertEqual(config.daily_posts, 5)
        self.assertEqual(config.official_images_dir, Path.cwd() / "custom_images")
        self.assertEqual(config.default_hashtags, ["#Alpha", "#Beta"])
        self.assertEqual(config.topic_depth, "standard")
        self.assertTrue(config.phone_export_auto)
        self.assertEqual(config.phone_export_dir, Path.cwd() / "sync_out")
        self.assertEqual(
            {field.name for field in fields(config)},
            {
                "project_root",
                "output_dir",
                "assets_dir",
                "official_images_dir",
                "state_dir",
                "openai_api_key",
                "openai_model",
                "openai_base_url",
                "video_width",
                "video_height",
                "daily_posts",
                "topic_depth",
                "default_hashtags",
                "phone_export_auto",
                "phone_export_dir",
                "telegram_bot_token",
                "telegram_chat_id",
                "telegram_as_document",
                "keep_render_layers",
            },
        )


if __name__ == "__main__":
    unittest.main()
