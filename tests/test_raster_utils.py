import numpy as np

from spatial.raster_utils import _alpha_to_uint8, _repair_empty_alpha


def test_alpha_to_uint8_preserves_constant_high_bit_opacity():
    alpha = np.full((2, 2), 65535, dtype=np.uint16)

    result = _alpha_to_uint8(alpha)

    assert result.dtype == np.uint8
    assert result.min() == 255
    assert result.max() == 255


def test_repair_empty_alpha_uses_rgb_visibility_mask():
    arr = np.array(
        [
            [[10, 20, 30, 0], [0, 0, 0, 0]],
            [[0, 5, 0, 0], [0, 0, 0, 0]],
        ],
        dtype=np.uint8,
    )

    repaired = _repair_empty_alpha(arr)

    assert repaired[:, :, 3].tolist() == [[255, 0], [255, 0]]
