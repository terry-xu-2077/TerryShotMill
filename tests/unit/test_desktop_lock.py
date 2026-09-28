import pytest
from shotmill.desktop_lock import desktop_data_lock


def test_lock_is_per_data_root_and_released_after_exception(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    with pytest.raises(ValueError, match="fixture"):
        with desktop_data_lock(left), desktop_data_lock(right):
            with pytest.raises(RuntimeError, match="请勿重复启动"):
                with desktop_data_lock(left):
                    pytest.fail("duplicate owner")
            raise ValueError("fixture")
    with desktop_data_lock(left):
        pass
