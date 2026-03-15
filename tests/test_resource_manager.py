"""
tests/test_resource_manager.py — Validate GPU resource manager.
"""


def test_resource_manager_init():
    """ResourceManager initialises without errors."""
    from worker.resource_manager import ResourceManager
    mgr = ResourceManager()
    assert mgr.gpu_available in (True, False)


def test_vram_info_returns_dict():
    """vram_info returns a dict (possibly empty on CPU-only)."""
    from worker.resource_manager import ResourceManager
    mgr = ResourceManager()
    info = mgr.vram_info()
    assert isinstance(info, dict)
