import subprocess
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analysis import charts  # noqa: E402

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def test_chart_filename_convention():
    assert charts.chart_filename("seasonal", "CPI", "2026-09-04") == "seasonal_CPI_2026-09-04.png"
    assert charts.chart_filename("forecast", "GDP_NOMINAL", "2026-09-04") == "forecast_GDP_NOMINAL_2026-09-04.png"


def test_importing_charts_does_not_import_pyplot():
    # Real subprocess, not an in-process assertion: some other test in this
    # same pytest process may have already imported pyplot for unrelated
    # reasons, which would make an in-process check order-dependent.
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, r'" + str(SCRIPTS_DIR) + "'); "
         "from analysis import charts; "
         "import sys as s; "
         "assert 'matplotlib.pyplot' not in s.modules, s.modules.keys()"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_save_figure_writes_a_valid_png(tmp_path):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 4, 9])
    path = tmp_path / "nested" / "chart.png"

    charts.save_figure(fig, path)

    assert path.exists()
    assert path.stat().st_size > 1000
    img = Image.open(path)
    img.verify()
    img2 = Image.open(path)
    assert img2.format == "PNG"
    assert img2.size[0] > 0 and img2.size[1] > 0


def test_save_figure_closes_the_figure(tmp_path):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    ax.plot([1, 2], [1, 2])
    fignum = fig.number

    charts.save_figure(fig, tmp_path / "chart.png")

    assert fignum not in plt.get_fignums()


def test_add_disclaimer_stamps_expected_text():
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    charts.add_disclaimer(fig)

    texts = [t.get_text() for t in fig.texts]
    assert charts.DISCLAIMER_TEXT in texts
    plt.close(fig)
