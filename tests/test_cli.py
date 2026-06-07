import pytest
import sys
from unittest.mock import patch, AsyncMock
from app.cli import main


class TestCLI:
    def test_cli_create_help(self):
        with patch('sys.argv', ['contento', 'create', '--help']):
            try:
                main()
            except SystemExit:
                pass

    def test_cli_plan_help(self):
        with patch('sys.argv', ['contento', 'plan', '--help']):
            try:
                main()
            except SystemExit:
                pass

    def test_cli_batch_help(self):
        with patch('sys.argv', ['contento', 'batch', '--help']):
            try:
                main()
            except SystemExit:
                pass

    def test_cli_export_help(self):
        with patch('sys.argv', ['contento', 'export', '--help']):
            try:
                main()
            except SystemExit:
                pass

    @pytest.mark.asyncio
    async def test_export_for_tts_plain(self, tmp_path):
        from app.cli import cmd_export_for_tts
        import json

        data = {
            "script": {
                "full_script": "This is the full script content.",
                "sections": [
                    {"timestamp": "0:00", "title": "Intro", "content": "Intro content."}
                ]
            }
        }

        input_file = tmp_path / "test_input.json"
        input_file.write_text(json.dumps(data))

        class Args:
            input = str(input_file)
            format = "plain"
            output = None

        with patch('builtins.print'):
            await cmd_export_for_tts(Args())

    @pytest.mark.asyncio
    async def test_export_for_tts_output(self, tmp_path):
        from app.cli import cmd_export_for_tts
        import json

        data = {
            "script": {
                "full_script": "Narration text for TTS.",
                "sections": []
            }
        }

        input_file = tmp_path / "test_input.json"
        input_file.write_text(json.dumps(data))

        output_file = tmp_path / "output.txt"

        class Args:
            input = str(input_file)
            format = "tts"
            output = str(output_file)

        await cmd_export_for_tts(Args())
        assert output_file.exists()
        assert "Narration text" in output_file.read_text()
