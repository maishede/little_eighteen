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
        return;
    }
    lastCommandTime = currentTime;
    console.log("发送控制命令:", command);
    fetch(`/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direction: command })
    }).catch(error => console.error('发送失败:', error));
}

/**
 * 启动指定的演示功能。
 * @param {string} demoName - 演示功能的名称。
 */
function startDemo(demoName) {
    fetch(`/demo/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ demo_name: demoName })
    }).then(r => r.json()).then(d => console.log(d.message));
}

/**
 * 停止当前正在运行的演示功能。
 */
function stopDemo() {
    fetch(`/demo/stop`, { method: 'POST' })
    .then(r => r.json()).then(d => console.log(d.message));
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
    }

    // --- 2. 摄像头控制逻辑 (大幅修改这里) ---
    const videoContainer = document.querySelector('.video-container'); // 视频容器
    const videoStream = document.getElementById('videoStream'); // img 标签
    const startCameraButton = document.getElementById('startCameraButton'); // 开启按钮
    const stopCameraButton = document.getElementById('stopCameraButton'); // 停止按钮

    let cameraStreaming = false; // 跟踪摄像头流是否激活

    /**
     * 设置摄像头UI状态。
     * @param {'off'|'streaming'} state - 摄像头状态。
     */
    function setCameraState(state) {
        videoContainer.classList.remove('show-controls');
        if (state === 'off') {
            cameraStreaming = false;
            videoContainer.classList.remove('streaming'); // 移除 streaming 状态类

            videoStream.src = ''; // 清空视频流源
            videoStream.alt = "视频流已停止。点击开启摄像头";
            videoStream.classList.add('video-placeholder'); // 恢复占位符样式

            // 显示开启按钮，隐藏停止按钮
            startCameraButton.classList.add('active');
            stopCameraButton.classList.remove('active'); // 确保停止按钮没有 active 类

            startCameraButton.textContent = '开启摄像头';
            startCameraButton.disabled = false;
        } else if (state === 'streaming') {
            cameraStreaming = true;
            videoContainer.classList.add('streaming'); // 添加 streaming 状态类
            videoStream.classList.remove('video-placeholder'); // 移除占位符样式

            // 隐藏开启按钮，停止按钮由 CSS 负责在 hover 时显示
            startCameraButton.classList.remove('active');
            stopCameraButton.classList.add('active'); // 停止按钮处于激活状态(虽然可能被opacity:0隐藏)

            // 设置视频流源
            videoStream.src = '/video_feed?t=' + Date.now();
            videoStream.alt = '摄像头视频流';

        }
    }

    // 初始设置摄像头状态为关闭
    setCameraState('off');

    // 点击视频容器的逻辑
    if (videoContainer) {
        videoContainer.addEventListener('click', (event) => {
            // 如果没在直播，或者点击的是开始按钮，或者点击的是停止按钮，都不处理
            // (停止按钮的逻辑由它自己的监听器处理，并阻止冒泡)
            if (!cameraStreaming) return;
            videoContainer.classList.toggle('show-controls');
        });
    }

    // 开启摄像头逻辑
    if (startCameraButton) {
        startCameraButton.addEventListener('click', (event) => {
            event.stopPropagation(); // 防止冒泡触发容器点击

            if (!cameraStreaming) {
                startCameraButton.textContent = '加载中...';
                startCameraButton.disabled = true;

                fetch('/camera/start', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.status === 'success') {
                        setCameraState('streaming');
                    } else {
                        alert('启动失败');
                        setCameraState('off');
                    }
                })
                .catch(e => {
                    console.error(e);
                    setCameraState('off');
                });
            }
        });
    }

    // 停止摄像头逻辑 (点击停止图标时触发)
    if (stopCameraButton) {
        stopCameraButton.addEventListener('click', (event) => {
            event.stopPropagation();
            if (cameraStreaming) {
                console.log("尝试停止摄像头流...");
                // 暂时显示停止中状态
                stopCameraButton.textContent = '停止中...';
                stopCameraButton.disabled = true;

                fetch('/camera/stop', {method: 'POST'})
                .then(() => {
                    setCameraState('off');
                    stopCameraButton.textContent = '停止';
                    stopCameraButton.disabled = false;
                })
                .catch(error => {
                    setCameraState('off');
                    stopCameraButton.textContent = '停止';
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