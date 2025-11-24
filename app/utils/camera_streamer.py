# app/utils/camera_streamer.py
import cv2
import threading
import time
import logging
import asyncio


class CameraStreamer:
    """
    负责管理摄像头视频流的类。
    Asyncio 优化版本：后台线程读取硬件，前台协程分发数据。
    """

    def __init__(self, camera_index: int, fps: int, resolution: tuple, logger: logging.Logger):
        self.camera_index = camera_index
        self.fps = fps
        self.resolution = resolution
        self.logger = logger
        self.cap = None
        self._is_streaming = False
        self._lock = threading.Lock()
        self._current_frame = None
        self._stop_event = threading.Event()
        self._capture_thread = None

        self.logger.info(f"CameraStreamer 初始化: Index={camera_index}, FPS={fps}, Res={resolution}")

    def start_camera_capture(self) -> bool:
        """启动摄像头捕获"""
        if self._is_streaming:
            self.logger.warning("摄像头已在运行")
            return True

        self.logger.info(f"正在打开摄像头 {self.camera_index}...")
        try:
            # 在树莓派上，建议指定 backend，有时能提高兼容性
            self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
            # self.cap = cv2.VideoCapture(self.camera_index)

            if not self.cap.isOpened():
                self.logger.error(f"无法打开摄像头 {self.camera_index}")
                return False

            # 2. 【绝对关键】强制设置为 MJPEG 格式
            # 树莓派 CSI 摄像头如果不加这一行，OpenCV 默认请求 YUYV 格式，
            # 在高分辨率下会导致带宽不足或直接读不到数据。
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

            # 设置参数
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 关键：减少延迟

            # --- 调试信息：打印实际生效的参数 ---
            actual_w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            actual_h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            self.logger.info(f"摄像头已启动。实际分辨率: {actual_w}x{actual_h}")
            fourcc = int(self.cap.get(cv2.CAP_PROP_FOURCC))
            # 将四字符代码解码为字符串
            codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
            self.logger.info(f"摄像头已就绪。实际分辨率: {actual_w}x{actual_h}, 编码: {codec}")
            self._is_streaming = True
            self._stop_event.clear()
            self._current_frame = None  # 重置当前帧

            # 启动采集线程
            self._capture_thread = threading.Thread(target=self._read_frames_loop, daemon=True)
            self._capture_thread.start()

            # 可选：等待一小会儿确保第一帧准备好（非阻塞式等待留给前端处理，这里只要线程启动即可）
            return True

        except Exception as e:
            self.logger.error(f"启动摄像头异常: {e}", exc_info=True)
            self._is_streaming = False
            return False

    def _read_frames_loop(self):
        """后台线程：负责从硬件读取帧"""
        self.logger.info("摄像头采集线程启动")
        while self._is_streaming and not self._stop_event.is_set():
            if self.cap:
                ret, frame = self.cap.read()
                if ret:
                    with self._lock:
                        self._current_frame = frame
                else:
                    self.logger.warning("无法读取帧，正在重试...")
                    time.sleep(0.5)  # 读取失败时稍作等待，防止CPU空转
                    continue

            # 控制采集帧率，避免占用过多CPU
            time.sleep(1 / self.fps)

        if self.cap:
            self.cap.release()
        self.logger.info("摄像头采集线程结束")

    async def generate_frames(self):
        """异步生成器：负责将帧编码并推送给Web客户端"""
        self.logger.info("开始推送视频流...")

        # 等待第一帧数据，防止返回空数据导致连接断开
        wait_count = 0
        while self._current_frame is None and self._is_streaming and wait_count < 50:
            await asyncio.sleep(0.1)
            wait_count += 1

        if self._current_frame is None:
            self.logger.error("等待第一帧超时")
            return

        while self._is_streaming:
            frame = None
            with self._lock:
                if self._current_frame is not None:
                    frame = self._current_frame.copy()

            if frame is None:
                await asyncio.sleep(0.01)
                continue

            # 编码图片 (CPU密集型操作)
            # 质量设为 60-80 之间，平衡画质和流畅度
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])

            if ret:
                # 构造 MJPEG 帧
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

            # 控制发送频率，释放控制权给 asyncio 事件循环
            await asyncio.sleep(1 / self.fps)

        self.logger.info("视频流推送结束")

    def stop_camera_capture(self):
        """停止摄像头"""
        self.logger.info("正在停止摄像头...")
        self._is_streaming = False
        self._stop_event.set()

        if self._capture_thread and self._capture_thread.is_alive():
            # 这里不要 join 太久，防止阻塞 async loop
            self._capture_thread.join(timeout=1.0)

        self._current_frame = None
        self.logger.info("摄像头已停止")

    def is_streaming_active(self) -> bool:
        return self._is_streaming
