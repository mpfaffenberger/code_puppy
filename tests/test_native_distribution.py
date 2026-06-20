from pathlib import Path


def test_native_distribution_covers_supported_installers():
    root = Path(__file__).parents[1]
    workflow = (root / ".github/workflows/native-release.yml").read_text()
    spec = (root / "packaging/mist.spec").read_text()

    assert "linux-x64.AppImage" in workflow
    assert "macos-arm64" in workflow
    assert "windows-x64" in workflow
    assert "mist.rb" in workflow
    assert "mist.json" in workflow
    assert 'name="mist"' in spec
