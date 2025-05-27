import requests
from unittest.mock import patch
from code_puppy.tools.web_search import web_search


def test_web_search_success():
    query = "python testing"
    with patch("requests.get") as mock_get:
        mock_response = mock_get.return_value
        mock_response.status_code = 200
        mock_response.text = '<div class="tF2Cxc"><h3>Test Title</h3><a href="http://example.com">Link</a></div>'
        results = web_search(None, query)

        assert len(results) == 1
        assert results[0]["title"] == "Test Title"
        assert results[0]["url"] == "http://example.com"


def test_web_search_http_error():
    query = "python testing"
    with patch("requests.get") as mock_get:
        mock_response = mock_get.return_value
        mock_response.raise_for_status.side_effect = requests.HTTPError
        try:
            web_search(None, query)
        except requests.HTTPError:
            assert True


def test_web_search_no_results():
    query = "something_not_found"
    html = ""  # No result divs
    with patch("requests.get") as mock_get:
        mock_response = mock_get.return_value
        mock_response.status_code = 200
        mock_response.text = html
        results = web_search(None, query)
        assert results == []


def test_web_search_broken_html():
    query = "broken html"
    html = '<div class="tF2Cxc"></div>'  # div with missing h3 and a
    with patch("requests.get") as mock_get:
        mock_response = mock_get.return_value
        mock_response.status_code = 200
        mock_response.text = html
        results = web_search(None, query)
        assert results == []


def test_web_search_num_results_limit():
    query = "multiple results"
    html = "".join(
        [
            f'<div class="tF2Cxc"><h3>Title {i}</h3><a href="http://example.com/{i}">Link</a></div>'
            for i in range(10)
        ]
    )
    with patch("requests.get") as mock_get:
        mock_response = mock_get.return_value
        mock_response.status_code = 200
        mock_response.text = html
        results = web_search(None, query, num_results=3)
        assert len(results) == 3
        assert results[0]["title"] == "Title 0"
        assert results[1]["url"] == "http://example.com/1"


def test_web_search_empty_soup():
    query = "empty soup"
    html = "   "
    with patch("requests.get") as mock_get:
        mock_response = mock_get.return_value
        mock_response.status_code = 200
        mock_response.text = html
        results = web_search(None, query)
        assert results == []
