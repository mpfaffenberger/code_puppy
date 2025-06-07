import requests


def fetch_latest_version(package_name):
    try:
        response = requests.get(f"https://pypi.org/pypi/{package_name}/json")
        response.raise_for_status()  # Raise an error for bad responses
        data = response.json()
        return data["info"]["version"]
    except requests.RequestException as e:
        print(f"Error fetching version: {e}")
        return None
