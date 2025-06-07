document.addEventListener('DOMContentLoaded', () => {
    const videoPanel = document.getElementById('videoPanel');
    const videoPlaceholder = document.getElementById('videoPlaceholder');
    const videoFeed = document.getElementById('videoFeed');
    const closeVideoButton = document.getElementById('closeVideoButton');
    const voiceControlButton = document.getElementById('voiceControlButton');

    let isVideoPlaying = false; // 跟踪视频状态
    let isVoiceRecording = false; // 跟踪语音录制状态
    let voiceTimeout; // 用于长按事件

    // --- sendCommand 函数：直接发送控制命令到树莓派后端 ---
    function sendCommand(command) {
        console.log("发送命令:", command);
        // 使用 Fetch API 发送 POST 请求
        fetch(`/control`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ direction: command }) // 将 command 作为 direction 发送
        })
        .then(response => {
            if (!response.ok) {
                // 如果响应状态码不是 2xx，抛出错误
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => console.log('命令发送成功:', data))
        .catch(error => console.error('发送命令失败:', error));
    }
    // 将 sendCommand 函数暴露到全局，以便 HTML 中的 onclick 可以调用
    window.sendCommand = sendCommand;

    // --- 视频控制逻辑 ---
    videoPlaceholder.addEventListener('click', () => {
        if (!isVideoPlaying) {
            // 开启视频流，实际应替换为树莓派摄像头的URL
            // 假设树莓派视频流地址为 /video_feed
            videoFeed.src = "/video_feed"; // <--- 替换为你的树莓派视频流地址
            videoFeed.classList.remove('hidden');
            videoPlaceholder.classList.add('hidden');
            closeVideoButton.classList.remove('hidden');
            isVideoPlaying = true;
            console.log("视频已开启");
        }
    });

    closeVideoButton.addEventListener('click', () => {
        if (isVideoPlaying) {
            videoFeed.src = ""; // 停止加载视频流
            videoFeed.classList.add('hidden');
            videoPlaceholder.classList.remove('hidden');
            closeVideoButton.classList.add('hidden');
            isVideoPlaying = false;
            console.log("视频已关闭");
        }
    });

    // --- 语音控制逻辑 (长按) ---
    voiceControlButton.addEventListener('touchstart', (e) => {
        e.preventDefault(); // 防止默认的长按行为，如弹出上下文菜单
        if (!isVoiceRecording) {
            voiceControlButton.classList.add('active'); // 添加激活样式
            voiceControlButton.querySelector('span').textContent = '正在听你说话...';
            console.log("开始语音录制");
            isVoiceRecording = true;
            // 假设长按超过 200ms 算作有效长按
            voiceTimeout = setTimeout(() => {
                // 在这里发送“开始录音”指令给树莓派
                sendCommand('start_voice_recognition');
            }, 200);
        }
    });

    voiceControlButton.addEventListener('touchend', () => {
        if (isVoiceRecording) {
            clearTimeout(voiceTimeout); // 清除长按计时器
            voiceControlButton.classList.remove('active'); // 移除激活样式
            voiceControlButton.querySelector('span').textContent = '按住说话';
            console.log("结束语音录制");
            // 模拟结束录音并发送数据
            sendCommand('end_voice_recognition'); // 发送“停止录音”指令给树莓派
            isVoiceRecording = false;
        }
    });

    // 也处理鼠标事件，以防在非触屏设备上测试
    voiceControlButton.addEventListener('mousedown', (e) => {
        e.preventDefault();
        if (!isVoiceRecording) {
            voiceControlButton.classList.add('active');
            voiceControlButton.querySelector('span').textContent = '正在听你说话...';
            console.log("开始语音录制");
            isVoiceRecording = true;
            voiceTimeout = setTimeout(() => {
                sendCommand('start_voice_recognition');
            }, 200);
        }
    });

    voiceControlButton.addEventListener('mouseup', () => {
        if (isVoiceRecording) {
            clearTimeout(voiceTimeout);
            voiceControlButton.classList.remove('active');
            voiceControlButton.querySelector('span').textContent = '按住说话';
            console.log("结束语音录制");
            sendCommand('end_voice_recognition');
            isVoiceRecording = false;
        }
    });
});