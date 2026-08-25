from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from mbti_tiktok_bot.config import load_config
from mbti_tiktok_bot.pipeline import PipelineResult
from mbti_tiktok_bot.telegram import TelegramError, deliver_results, send_album


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload


class TelegramTests(unittest.TestCase):
    def _config(self, root: Path):
        return replace(
            load_config(Path.cwd()),
            project_root=root,
            output_dir=root / "out",
            telegram_bot_token="test-token",
            telegram_chat_id="12345",
            telegram_as_document=True,
        )

    def _slides(self, root: Path, count: int) -> list[Path]:
        slides_dir = root / "slides"
        slides_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for index in range(count):
            path = slides_dir / f"slide_{index + 1:02d}.png"
            Image.new("RGB", (8, 8), (255, 255, 255)).save(path)
            paths.append(path)
        return paths

    def test_send_album_batches_into_groups_of_ten(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = self._config(root)
            paths = self._slides(root, 12)

            with patch("mbti_tiktok_bot.telegram.requests.post", return_value=FakeResponse({"ok": True})) as post_mock:
                sent = send_album(config, paths)

            self.assertEqual(sent, 12)
            # 12 slides is two albums, not one oversized request.
            self.assertEqual(post_mock.call_count, 2)
            self.assertTrue(all(call.args[0].endswith("/sendMediaGroup") for call in post_mock.call_args_list))

    def test_send_album_uses_documents_to_avoid_re_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = self._config(root)
            paths = self._slides(root, 3)

            with patch("mbti_tiktok_bot.telegram.requests.post", return_value=FakeResponse({"ok": True})) as post_mock:
                send_album(config, paths)

            media = json.loads(post_mock.call_args.kwargs["data"]["media"])
            self.assertEqual([item["type"] for item in media], ["document"] * 3)

    def test_send_album_falls_back_to_single_upload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = self._config(root)
            paths = self._slides(root, 1)

            with patch("mbti_tiktok_bot.telegram.requests.post", return_value=FakeResponse({"ok": True})) as post_mock:
                send_album(config, paths)

            # sendMediaGroup rejects a one-item album.
            self.assertTrue(post_mock.call_args.args[0].endswith("/sendDocument"))

    def test_send_album_raises_on_api_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = self._config(root)
            paths = self._slides(root, 2)

            with patch(
                "mbti_tiktok_bot.telegram.requests.post",
                return_value=FakeResponse({"ok": False, "description": "chat not found"}),
            ):
                with self.assertRaises(TelegramError):
                    send_album(config, paths)

    def test_deliver_results_sends_caption_as_its_own_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = self._config(root)
            paths = self._slides(root, 7)
            caption_path = root / "caption.txt"
            caption_path.write_text("本文\n#MBTI", encoding="utf-8")

            result = PipelineResult(
                output_dir=root,
                package_path=root / "package.json",
                caption_path=caption_path,
                title="INTJが本命だけに見せる距離の縮め方",
                mbti_type="INTJ",
                daily_slot=1,
                global_post_index=1,
                media_paths=paths,
            )

            with patch("mbti_tiktok_bot.telegram.requests.post", return_value=FakeResponse({"ok": True})) as post_mock:
                delivery = deliver_results(config, [result])

            self.assertEqual(delivery.sent_posts, 1)
            self.assertEqual(delivery.sent_files, 7)
            methods = [call.args[0].rsplit("/", 1)[-1] for call in post_mock.call_args_list]
            self.assertEqual(methods, ["sendMessage", "sendMediaGroup", "sendMessage"])
            self.assertEqual(post_mock.call_args_list[-1].kwargs["data"]["text"], "本文\n#MBTI")


if __name__ == "__main__":
    unittest.main()
