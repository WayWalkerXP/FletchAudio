from metadata_collector import config


def test_archive_directory_setting_is_saved_and_reloaded(tmp_path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_FILE", settings_file)

    config.save_settings({"archive_dir": "D:/ArchivedBooks", "theme": "Dark"})

    loaded = config.load_settings()

    assert loaded["archive_dir"] == "D:/ArchivedBooks"
    assert loaded["theme"] == "Dark"
    assert "conversion_output_dir" in loaded
