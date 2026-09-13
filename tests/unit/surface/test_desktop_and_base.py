import pytest

from cua.surface.base import Surface
from cua.surface.desktop import DesktopSurface

pytestmark = pytest.mark.unit


def test_surface_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        Surface()


def test_desktop_surface_is_a_declared_but_unimplemented_seam():
    with pytest.raises(NotImplementedError, match="design seam"):
        DesktopSurface()


def test_desktop_surface_conforms_to_the_surface_interface():
    """It must be a real Surface subclass (same method set), not just a
    same-named class -- that's what makes swapping it in a non-event."""
    assert issubclass(DesktopSurface, Surface)
