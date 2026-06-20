"""
Fullscreen capture module for SnapEdit.

Uses the `mss` library to capture the entire screen or a specific monitor.
Supports multi-monitor setups by allowing capture of individual monitors
or the combined virtual desktop.

Functions:
    capture_fullscreen: Capture a full monitor screen and return as QPixmap.
    get_monitor_count: Return the number of available monitors.
    get_monitor_info: Return geometry info for a specific monitor.
"""
import mss
from PIL import Image
from PyQt6.QtGui import QPixmap, QImage


def pil_to_qpixmap(pil_image: Image.Image) -> QPixmap:
    """Convert a PIL Image to a QPixmap.

    Args:
        pil_image: The source PIL Image to convert.

    Returns:
        A QPixmap containing the image data.
    """
    if pil_image.mode != 'RGBA':
        pil_image = pil_image.convert('RGBA')
    data = pil_image.tobytes('raw', 'RGBA')
    qimage = QImage(
        data,
        pil_image.width,
        pil_image.height,
        QImage.Format.Format_RGBA8888
    )
    return QPixmap.fromImage(qimage)


def capture_fullscreen(monitor_index: int = 0) -> QPixmap:
    """Capture the full screen of a monitor and return as QPixmap.

    Args:
        monitor_index: Which monitor to capture.
                       0 = combined virtual desktop (all monitors stitched).
                       1 = primary monitor.
                       2 = second monitor, etc.
                       Defaults to 0 (all monitors).

    Returns:
        A QPixmap containing the captured screenshot.

    Raises:
        IndexError: If monitor_index exceeds the number of available monitors.
        RuntimeError: If the screen capture fails.
    """
    try:
        with mss.mss() as sct:
            # Validate monitor index
            if monitor_index < 0 or monitor_index >= len(sct.monitors):
                raise IndexError(
                    f"Monitor index {monitor_index} out of range. "
                    f"Available: 0-{len(sct.monitors) - 1} "
                    f"(0 = all monitors, 1-{len(sct.monitors) - 1} = individual)"
                )

            monitor = sct.monitors[monitor_index]
            screenshot = sct.grab(monitor)

            # Convert mss screenshot to PIL Image
            # mss returns BGRA data, PIL expects RGBA
            pil_image = Image.frombytes(
                'RGB',
                (screenshot.width, screenshot.height),
                screenshot.rgb
            )

            return pil_to_qpixmap(pil_image)

    except IndexError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to capture screen: {e}") from e


