"""src/tracing/centerline.py: the tracer gives the same line on every CPU.

Issue #116: two of GitHub's Linux runners placed step 13's vertices 0.34 m
apart along the same road. NumPy picks its float64 exp by the CPU (an AVX-512
kernel where there is one, the C library's elsewhere), the two differ in the
last bit of some results, and on a straight north-south road the first
road-centring pass reads the ink exactly on cell edges, where that last bit
decides which cell is read. Here NumPy's exp is made the C library's (one
CPU) and then one ulp higher (another CPU), and the tracer's results must not
change by a single bit.
"""

import math

import pytest

pytest.importorskip(
    "osgeo",
    reason="GDAL's Python bindings are in the build's .venv (./build.sh env), "
    "not the lint tools",
)
import numpy as np
from scipy import ndimage

from src.tracing import centerline

pytestmark = pytest.mark.build
NUMPY_EXP = np.exp


def c_library_exp(x, *args, **kwargs):
    """NumPy's exp as a CPU without AVX-512 gives it: the C library's."""
    del args, kwargs
    return np.vectorize(math.exp, otypes=[np.float64])(x)


def one_ulp_high_exp(x, *args, **kwargs):
    """NumPy's exp one ulp higher, as another CPU's exp may give it."""
    return np.nextafter(c_library_exp(x, *args, **kwargs), np.inf)


def on_two_cpus(monkeypatch, run):
    """Runs run() with NumPy's exp as on one CPU, then as on another.

    Returns:
        The two results.
    """
    monkeypatch.setattr(np, "exp", c_library_exp)
    first = run()
    monkeypatch.setattr(np, "exp", one_ulp_high_exp)
    second = run()
    monkeypatch.setattr(np, "exp", NUMPY_EXP)
    return first, second


def road_path(xmin=-1234.5678, ymin=-987.6543):
    """A path as trace() makes it: cell centres, north 120 m, then north-east.

    Returns:
        (path, xmin, ymin): the path's points (m) and the grid's origin.
    """
    col, rows = 37, np.arange(5, 125)
    north = [(xmin + col + 0.5, ymin + r + 0.5) for r in rows]
    bend = [
        (xmin + col + k + 0.5, ymin + rows[-1] + k + 0.5) for k in range(1, 40)
    ]
    return np.array(north + bend, dtype=np.float64), xmin, ymin


def test_libm_exp_is_the_c_librarys_exp():
    x = np.array([[-0.5, -3.125, 0.0], [-12.75, -1e-9, -40.0]])
    got = centerline.libm_exp(x)
    assert got.shape == x.shape
    assert got.dtype == np.float64
    assert [float(v) for v in got.ravel()] == [math.exp(v) for v in x.ravel()]
    assert centerline.libm_exp(-2.0).shape == ()


def test_libm_exp_ignores_numpys_exp(monkeypatch):
    x = -0.5 * np.linspace(0, 6, 241) ** 2
    first, second = on_two_cpus(monkeypatch, lambda: centerline.libm_exp(x))
    assert np.array_equal(first, second)


def test_gaussian_filter1d_is_scipys_filter():
    f = np.random.default_rng(116).normal(size=300).cumsum()
    for sigma in (2.0, 8.0, 25.0):
        np.testing.assert_allclose(
            centerline.gaussian_filter1d(f, sigma),
            ndimage.gaussian_filter1d(f, sigma, mode="nearest"),
            rtol=0,
            atol=1e-12,
        )


def test_smooth_is_the_same_on_every_cpu(monkeypatch):
    path, _, _ = road_path()
    first, second = on_two_cpus(
        monkeypatch, lambda: centerline.smooth(path, 8.0)
    )
    assert np.array_equal(first, second)


def test_robust_offsets_are_the_same_on_every_cpu(monkeypatch):
    m = np.random.default_rng(80).normal(scale=0.7, size=900)
    m[100:160] = np.nan  # a junction, where nothing is read
    m[400] = 9.0  # a reading off the trend: dropped
    first, second = on_two_cpus(
        monkeypatch, lambda: centerline.robust_offsets(m, 25.0)
    )
    assert np.array_equal(first, second)


def test_road_centre_is_the_same_on_every_cpu(monkeypatch):
    """The first centring pass on a north-south road, as trace() runs it."""
    path, xmin, ymin = road_path()
    ink = np.zeros((140, 120), bool)
    ink[:, 32:34] = True  # the west casing
    ink[:, 41:43] = True  # the east casing: a road 9 m wide

    def centre():
        line = centerline.resample(centerline.smooth(path, 8.0), 1.0)
        return centerline.edge_offsets(line, ink, xmin, ymin)

    (first, width1), (second, width2) = on_two_cpus(monkeypatch, centre)
    assert width1 == width2
    assert np.array_equal(first, second, equal_nan=True)
