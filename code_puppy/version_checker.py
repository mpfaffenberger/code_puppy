import httpx

from code_puppy.tools.common import console


def normalize_version(version_str):
    if not version_str:
        return version_str
    return version_str.lstrip("v")


def versions_are_equal(current, latest):
    return normalize_version(current) == normalize_version(latest)


def fetch_latest_version(package_name):
    try:
        response = httpx.get(f"https://pypi.org/pypi/{package_name}/json")
        response.raise_for_status()  # Raise an error for bad responses
        data = response.json()
        return data["info"]["version"]
    except Exception as e:
        print(f"Error fetching version: {e}")
        return None


def default_version_mismatch_behavior(current_version):
    latest_version = fetch_latest_version("code-puppy")
    console.print(f"Current version: {current_version}")
    console.print(f"Latest version: {latest_version}")
    if latest_version and latest_version != current_version:
        console.print(
            f"[bold yellow]A new version of code puppy is available: {latest_version}[/bold yellow]"
        )
        console.print("[bold green]Please consider updating![/bold green]")
