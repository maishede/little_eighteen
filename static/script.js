// static/script.js

// 用于限制命令发送频率的变量 (节流)
let lastCommandTime = 0;
const commandThrottleInterval = 50; // 限制每 50 毫秒发送一次命令

/**
 * 发送控制命令到后端。
 * @param {string} command - 控制命令字符串，例如 'move_forward', 'stop'。
 */
function sendCommand(command) {
    const currentTime = Date.now();
    if (currentTime - lastCommandTime < commandThrottleInterval) {
        // 如果距离上次发送命令的时间太短，则不发送
        console.log("命令发送过于频繁，已节流:", command);
        return;
    }
    lastCommandTime = currentTime;

    console.log("发送控制命令:", command);
    fetch(`/control`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ direction: command })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => console.log('控制命令发送成功:', data))
    .catch(error => console.error('发送控制命令失败:', error));
}

/**
 * 启动指定的演示功能。
 * @param {string} demoName - 演示功能的名称。
 */
function startDemo(demoName) {
    console.log("启动演示功能:", demoName);
    fetch(`/demo/start`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ demo_name: demoName })
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => { throw new Error(err.detail || `HTTP error! status: ${response.status}`); });
        }
        return response.json();
    })
    .then(data => console.log('演示启动成功:', data.message))
    .catch(error => console.error('启动演示失败:', error.message));
}

/**
 * 停止当前正在运行的演示功能。
 */
function stopDemo() {
    console.log("停止演示功能。");
    fetch(`/demo/stop`, {
        method: 'POST'
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => { throw new Error(err.detail || `HTTP error! status: ${response.status}`); });
        }
        return response.json();
    })
    .then(data => console.log('演示停止成功:', data.message))
    .catch(error => console.error('停止演示失败:', error.message));
}


// --- 页面加载完成后的事件绑定 ---
document.addEventListener('DOMContentLoaded', () => {
    // --- 1. 控制按钮事件绑定 (使用事件委托) ---
    const controlGrid = document.querySelector('.control-grid');
    if (controlGrid) {
        controlGrid.addEventListener('click', (event) => {
            // 找到被点击的最近的 .btn-control 元素
            const targetButton = event.target.closest('.btn-control');
            if (targetButton && targetButton.dataset.command) {
                const command = targetButton.dataset.command;
                sendCommand(command);
            }
        });
    } else {
        console.warn("未找到 .control-grid 元素，手动控制按钮可能无法工作。");
    }

    // --- 2. 摄像头控制逻辑 (大幅修改这里) ---
    const videoContainer = document.querySelector('.video-container'); // 视频容器
    const videoStream = document.getElementById('videoStream'); // img 标签
    const cameraOverlay = document.getElementById('cameraOverlay'); // 摄像头控制覆盖层
    const startCameraButton = document.getElementById('startCameraButton'); // 开启按钮
    const stopCameraButton = document.getElementById('stopCameraButton'); // 停止按钮

    let cameraStreaming = false; // 跟踪摄像头流是否激活

    /**
     * 设置摄像头UI状态。
     * @param {'off'|'streaming'} state - 摄像头状态。
     */
    function setCameraState(state) {
        if (state === 'off') {
            cameraStreaming = false;
            videoContainer.classList.remove('streaming'); // 移除 streaming 状态类
            videoStream.src = ''; // 清空视频流源
            videoStream.alt = "视频流已停止。点击开启摄像头";
            videoStream.classList.add('video-placeholder'); // 恢复占位符样式

            // 显示开启按钮，隐藏停止按钮
            startCameraButton.classList.add('active');
            stopCameraButton.classList.remove('active'); // 确保停止按钮没有 active 类
            cameraOverlay.style.pointerEvents = 'auto'; // 允许点击 overlay 上的按钮 (因为 start 按钮在上面)
            videoContainer.style.cursor = 'default'; // 恢复默认光标
        } else if (state === 'streaming') {
            cameraStreaming = true;
            videoContainer.classList.add('streaming'); // 添加 streaming 状态类
            videoStream.classList.remove('video-placeholder'); // 移除占位符样式

            // 隐藏开启按钮，停止按钮由 CSS 负责在 hover 时显示
            startCameraButton.classList.remove('active');
            cameraOverlay.style.pointerEvents = 'auto'; // 允许点击事件，但停止按钮的 pointer-events 由 CSS 控制
            videoContainer.style.cursor = 'pointer'; // 鼠标悬停在视频上时显示可点击光标

            // 设置视频流源
//            videoStream.src = '/video_feed';
            videoStream.src = '/video_feed?t=' + Date.now();
            videoStream.alt = '摄像头视频流';
        }
    }

    // 初始设置摄像头状态为关闭
    setCameraState('off');


    // 开启摄像头逻辑
    if (startCameraButton) {
        startCameraButton.addEventListener('click', () => {
            if (!cameraStreaming) {
                console.log("尝试向后端发送启动摄像头服务请求...");
                // 暂时显示加载状态，以免用户多次点击
                startCameraButton.textContent = '加载中...';
                startCameraButton.disabled = true;

                fetch('/camera/start', {
                    method: 'POST'
                })
                .then(response => {
                    if (!response.ok) {
                        return response.json().then(err => { throw new Error(err.detail || `HTTP error! status: ${response.status}`); });
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('启动摄像头服务响应:', data);
                    if (data.status === 'success') {
                        setCameraState('streaming'); // 设置为流式传输状态
                        startCameraButton.textContent = '开启摄像头'; // 恢复文本，但CSS会隐藏它
                        startCameraButton.disabled = false;
                        console.log("摄像头服务已启动，正在从 /video_feed 获取视频流。");
                    } else {
                        alert('启动摄像头服务失败: ' + (data.message || '未知错误'));
                        setCameraState('off'); // 保持关闭状态
                        startCameraButton.textContent = '开启摄像头'; // 恢复文本
                        startCameraButton.disabled = false;
                    }
                })
                .catch(error => {
                    console.error('开启摄像头服务失败:', error.message);
                    alert('无法开启摄像头服务。请检查服务器日志。');
                    setCameraState('off'); // 保持关闭状态
                    startCameraButton.textContent = '开启摄像头'; // 恢复文本
                    startCameraButton.disabled = false;
                });
            }
        });
    }

    // 停止摄像头逻辑 (点击停止图标时触发)
    if (stopCameraButton) {
        stopCameraButton.addEventListener('click', () => {
            if (cameraStreaming) {
                console.log("尝试停止摄像头流...");
                // 暂时显示停止中状态
                stopCameraButton.textContent = '停止中...';
                stopCameraButton.disabled = true;

                fetch('/camera/stop', {
                    method: 'POST'
                })
                .then(response => {
                    if (!response.ok) {
                        return response.json().then(err => { throw new Error(err.detail || `HTTP error! status: ${response.status}`); });
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('停止摄像头流成功:', data.message);
                    setCameraState('off'); // 设置为关闭状态
                    stopCameraButton.textContent = '停止'; // 恢复文本
                    stopCameraButton.disabled = false;
                })
                .catch(error => {
                    console.error('停止摄像头流失败:', error.message);
                    alert('无法停止摄像头流。');
                    setCameraState('off'); // 确保恢复到关闭状态
                    stopCameraButton.textContent = '停止'; // 恢复文本
                    stopCameraButton.disabled = false;
                });
            }
        });
    }

    // --- 3. 文本命令发送 ---
    const textCommandInput = document.getElementById('textCommandInput');
    const sendTextCommandButton = document.getElementById('sendTextCommandButton');

    if (sendTextCommandButton && textCommandInput) {
        sendTextCommandButton.addEventListener('click', () => {
            const text = textCommandInput.value.trim();
            if (text) {
                console.log("发送文本命令:", text);
                fetch('/cmd', { // 注意：这里是 /cmd 路由，不是 /control
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: text })
                })
                .then(response => {
                    if (!response.ok) {
                        return response.json().then(err => { throw new Error(err.detail || `HTTP error! status: ${response.status}`); });
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('文本命令发送成功:', data);
                    textCommandInput.value = ''; // 清空输入框
                })
                .catch(error => console.error('发送文本命令失败:', error.message));
            } else {
                console.warn("文本命令为空。");
            }
        });
        // 允许按回车键发送
        textCommandInput.addEventListener('keypress', (event) => {
            if (event.key === 'Enter') {
                sendTextCommandButton.click();
            }
        });
    }

    // --- 4. 语音识别功能 (ASR WebSocket) ---
    const startAsrButton = document.getElementById('startAsrButton');
    const stopAsrButton = document.getElementById('stopAsrButton');
    const asrOutput = document.getElementById('asrOutput');

    let websocket;
    let isAsrActive = false;

    // ASR WebSocket 连接管理
    function connectAsrWebSocket() {
        if (websocket && websocket.readyState === WebSocket.OPEN) {
            console.log("WebSocket 已经连接。");
            return;
        }

        // 获取当前域名和端口
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        const wsUrl = `${protocol}//${host}/asr`;

        websocket = new WebSocket(wsUrl);

        websocket.onopen = (event) => {
            console.log("ASR WebSocket 已连接:", event);
            asrOutput.textContent = "等待语音...";
            isAsrActive = true;
            startAsrButton.textContent = '已连接'; // 更新按钮状态
            startAsrButton.disabled = true;
            stopAsrButton.disabled = false;
        };

        websocket.onmessage = (event) => {
            console.log("ASR WebSocket 收到消息:", event.data);
            asrOutput.textContent = event.data;
        };

        websocket.onerror = (event) => {
            console.error("ASR WebSocket 错误:", event);
            asrOutput.textContent = "语音识别服务错误。";
            isAsrActive = false;
            startAsrButton.textContent = '开始语音';
            startAsrButton.disabled = false;
            stopAsrButton.disabled = true;
            if (websocket) websocket.close(); // 发生错误时关闭连接
        };

        websocket.onclose = (event) => {
            console.log("ASR WebSocket 已关闭:", event);
            asrOutput.textContent = "语音识别服务已停止。";
            isAsrActive = false;
            startAsrButton.textContent = '开始语音';
            startAsrButton.disabled = false;
            stopAsrButton.disabled = true;
            websocket = null; // 清除 WebSocket 实例
        };
    }

    function disconnectAsrWebSocket() {
        if (websocket && websocket.readyState === WebSocket.OPEN) {
            websocket.close();
            console.log("ASR WebSocket 已请求关闭。");
        } else {
            console.log("ASR WebSocket 未连接或已关闭。");
        }
        isAsrActive = false;
        startAsrButton.textContent = '开始语音';
        startAsrButton.disabled = false;
        stopAsrButton.disabled = true;
    }


    if (startAsrButton) {
        startAsrButton.addEventListener('click', connectAsrWebSocket);
    }
    if (stopAsrButton) {
        stopAsrButton.addEventListener('click', disconnectAsrWebSocket);
    }
    // 初始状态，停止按钮禁用
    if (stopAsrButton) stopAsrButton.disabled = true;

    // --- 5. 演示功能逻辑 ---
    const demoSelect = document.getElementById('demoSelect');
    const startDemoButton = document.getElementById('startDemoButton');
    const stopDemoButton = document.getElementById('stopDemoButton');

    if (startDemoButton && demoSelect) {
        startDemoButton.addEventListener('click', () => {
            const selectedDemo = demoSelect.value;
            if (selectedDemo) {
                startDemo(selectedDemo);
            } else {
                alert("请选择一个演示模式。");
            }
        });
    }

    if (stopDemoButton) {
        stopDemoButton.addEventListener('click', stopDemo);
    }
});