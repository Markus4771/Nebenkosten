from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app import __version__
from app.main import health
from app.update_manager import CURRENT_VERSION


ROOT = Path(__file__).resolve().parents[1]


def test_version_is_consistent():
    assert __version__ == CURRENT_VERSION == (ROOT / "version.txt").read_text().strip()
    assert health()["version"] == __version__


def test_all_templates_compile():
    template_dir = ROOT / "app" / "templates"
    environment = Environment(loader=FileSystemLoader(template_dir))
    for path in template_dir.glob("*.html"):
        environment.get_template(path.name)


def test_tax_advisor_content_is_inside_content_block():
    source = (ROOT / "app" / "templates" / "tax_advisor.html").read_text(encoding="utf-8")
    assert source.index("{% block content %}") < source.index("Fehlende Belege")
    assert source.index("Fehlende Belege") < source.rindex("{% endblock %}")
