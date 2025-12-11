// static/script.js

// 节流控制：防止点击过快发送过多请求
let lastCommandTime = 0;
const commandThrottleInterval = 50;

/**
 * 发送运动控制命令到后端
 */
function sendCommand(command) {
    const currentTime = Date.now();
    if (currentTime - lastCommandTime < commandThrottleInterval) {
        return;
    }
    lastCommandTime = currentTime;

    // 增加触觉反馈 (如果设备支持)
    if (navigator.vibrate) navigator.vibrate(10);

    fetch(`/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direction: command })
    }).catch(error => console.error('发送失败:', error));
}

/**
 * 发送速度设置命令到后端
 * 使用节流防止滑动时请求过于频繁
 */
let lastSpeedTime = 0;
const speedThrottleInterval = 100; // 100ms 发送一次

function setSpeed(speedVal) {
    const currentTime = Date.now();
    if (currentTime - lastSpeedTime < speedThrottleInterval) {
        return;
    }
    lastSpeedTime = currentTime;

    fetch(`/control/speed`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ speed: parseInt(speedVal) })
    })
    .then(r => r.json())
    .then(data => console.log('速度已更新:', data))
    .catch(e => console.error('调速失败:', e));
}

// 页面加载完成
document.addEventListener('DOMContentLoaded', () => {

    // 1. 方向控制按钮绑定
    const controlGrid = document.querySelector('.control-grid');
    if (controlGrid) {
        // 使用事件委托处理所有按钮点击
        controlGrid.addEventListener('click', (event) => {
            const targetButton = event.target.closest('.btn-control');
            if (targetButton && targetButton.dataset.command) {
                sendCommand(targetButton.dataset.command);
            }
        });

        // 增加触摸支持 (防止点击延迟)
        controlGrid.addEventListener('touchstart', (event) => {
            const targetButton = event.target.closest('.btn-control');
            if (targetButton) {
                event.preventDefault(); // 防止触发 click
                if (targetButton.dataset.command) {
                    sendCommand(targetButton.dataset.command);
                    targetButton.classList.add('active-touch'); // 模拟按压效果
                }
            }
        });

        controlGrid.addEventListener('touchend', (event) => {
             const targetButton = event.target.closest('.btn-control');
             if (targetButton) targetButton.classList.remove('active-touch');
        });
    }

    // 2. 速度滑块逻辑
    const speedRange = document.getElementById('speedRange');
    const speedValue = document.getElementById('speedValue');

    if (speedRange && speedValue) {
        // 监听输入事件 (拖动时实时更新)
        speedRange.addEventListener('input', (e) => {
            const val = e.target.value;
            speedValue.textContent = val;
            setSpeed(val);
        });
    }

    // 3. 摄像头控制逻辑
    const videoContainer = document.querySelector('.video-container');
    const videoStream = document.getElementById('videoStream');
    const startCameraButton = document.getElementById('startCameraButton');
    const stopCameraButton = document.getElementById('stopCameraButton');
    let cameraStreaming = false;

    function setCameraState(state) {
        videoContainer.classList.remove('show-controls');
        if (state === 'off') {
            cameraStreaming = false;
            videoContainer.classList.remove('streaming');
            videoStream.src = '';
            videoStream.classList.add('video-placeholder');
            startCameraButton.classList.add('active');
            stopCameraButton.classList.remove('active');
            startCameraButton.disabled = false;
            stopCameraButton.disabled = false;
        } else if (state === 'streaming') {
            cameraStreaming = true;
            videoContainer.classList.add('streaming');
            videoStream.classList.remove('video-placeholder');
            startCameraButton.classList.remove('active');
            stopCameraButton.classList.add('active');
            videoStream.src = '/video_feed?t=' + Date.now();
        }
    }

    setCameraState('off');

    if (videoContainer) {
        videoContainer.addEventListener('click', () => {
            if (cameraStreaming) videoContainer.classList.toggle('show-controls');
        });
    }

    if (startCameraButton) {
        startCameraButton.addEventListener('click', (e) => {
            e.stopPropagation();
            if (!cameraStreaming) {
                startCameraButton.disabled = true;
                fetch('/camera/start', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.status === 'success') setCameraState('streaming');
                    else { alert('启动失败'); setCameraState('off'); }
                })
                .catch(() => setCameraState('off'));
            }
        });
    }

    if (stopCameraButton) {
        stopCameraButton.addEventListener('click', (e) => {
            e.stopPropagation();
            if (cameraStreaming) {
                stopCameraButton.disabled = true;
                fetch('/camera/stop', { method: 'POST' })
                .then(() => { setCameraState('off'); stopCameraButton.disabled = false; })
                .catch(() => { setCameraState('off'); stopCameraButton.disabled = false; });
            }
        });
    }
});