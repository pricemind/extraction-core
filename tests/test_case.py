from pathlib import Path


def get_html() -> str:
    html_path = Path(__file__).resolve().parent.joinpath('website.html')
    with open(html_path, 'r') as file:
        return str(file.read())
