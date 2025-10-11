prompt = """Walmart specific rules:
 - You are operating inside Walmart Global Tech! Yay!
 - Always use uv when working with python, and always use --index-url https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple --allow-insecure-host pypi.ci.artifacts.walmart.com
 - Use WCAG 2.2 Level AA guidelines when coding front-end applications.
 - When you generate the front-end code, inform the user that it conforms to the WCAG 2.2 Level AA guidelines.
 - When something like brew or winget fails to install a piece of software due to some connection error or something like that
    Try setting these proxies in the environment variables for just that command (please do it inline if possible)
    - HTTP_PROXY=http://sysproxy.wal-mart.com:8080
    - HTTPS_PROXY=http://sysproxy.wal-mart.com:8080
"""
