import pytest
from unittest.mock import patch, MagicMock
from infrastructure.providers.render.smart_cropping_service import SmartCroppingService, HAS_ULTRALYTICS

@pytest.fixture
def service():
    with patch("infrastructure.providers.render.smart_cropping_service.YOLO", create=True):
        with patch("infrastructure.providers.render.smart_cropping_service.HAS_ULTRALYTICS", True):
            return SmartCroppingService(model_name="yolov8n.pt", target_ratio=9/16)

def test_fallback_when_no_ultralytics():
    with patch("infrastructure.providers.render.smart_cropping_service.HAS_ULTRALYTICS", False):
        srv = SmartCroppingService()
        crop_cmd = srv.get_crop_filter("test.mp4", 1080, 1920)
        assert crop_cmd == "crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2"

def test_fallback_when_cv2_fails(service):
    with patch("infrastructure.providers.render.smart_cropping_service.cv2", create=True) as mock_cv2:
        mock_cv2.CAP_PROP_FRAME_COUNT = 7
        mock_cv2.CAP_PROP_FPS = 5
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_cv2.VideoCapture.return_value = mock_cap

        crop_cmd = service.get_crop_filter("test.mp4", 1080, 1920)
        assert crop_cmd == "crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2"

def test_crop_horizontal_video_centered_on_person(service):
    with patch("infrastructure.providers.render.smart_cropping_service.cv2", create=True) as mock_cv2:
        mock_cv2.CAP_PROP_FRAME_COUNT = 7
        mock_cv2.CAP_PROP_FPS = 5
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            7: 100,
            5: 30,
            3: 1920,
            4: 1080
        }[prop]
        mock_cap.read.return_value = (True, "mock_frame")
        mock_cv2.VideoCapture.return_value = mock_cap

        mock_results = MagicMock()
        mock_box = MagicMock()
        # Mocking the specific list structure the code expects
        mock_box.xyxy = [[200, 100, 400, 900]]
        # The service code does: x1, y1, x2, y2 = largest_box.xyxy[0].tolist()
        # Let's mock xyxy[0] so it has a tolist method
        class MockXYXY:
            def tolist(self): return [200, 100, 400, 900]
            def __getitem__(self, idx): return [200, 100, 400, 900][idx]
        mock_box.xyxy = [MockXYXY()]

        mock_results.boxes = [mock_box]
        service.model.predict.return_value = [mock_results]

        crop_cmd = service.get_crop_filter("test.mp4", 1080, 1920)
        assert crop_cmd == "crop=1080:1920:0:0" or crop_cmd == "crop=1080:1920:0:(in_h-1920)/2"


def test_crop_horizontal_video_centered_on_person_right(service):
    with patch("infrastructure.providers.render.smart_cropping_service.cv2", create=True) as mock_cv2:
        mock_cv2.CAP_PROP_FRAME_COUNT = 7
        mock_cv2.CAP_PROP_FPS = 5
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            7: 100,
            5: 30,
            3: 1920,
            4: 1080
        }[prop]
        mock_cap.read.return_value = (True, "mock_frame")
        mock_cv2.VideoCapture.return_value = mock_cap

        mock_results = MagicMock()
        mock_box = MagicMock()
        class MockXYXY:
            def tolist(self): return [1600, 100, 1700, 900]
            def __getitem__(self, idx): return [1600, 100, 1700, 900][idx]
        mock_box.xyxy = [MockXYXY()]

        mock_results.boxes = [mock_box]
        service.model.predict.return_value = [mock_results]

        crop_cmd = service.get_crop_filter("test.mp4", 1080, 1920)
        assert crop_cmd == "crop=1080:1920:2333:0" or crop_cmd == "crop=1080:1920:840:(in_h-1920)/2"
